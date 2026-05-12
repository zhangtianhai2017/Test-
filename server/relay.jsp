<%--
  Relay JSP — drop into Tomcat webapps/ROOT/ (or any context).
  Single-file command-relay queue between a remote operator (me) and a
  Windows agent that actually executes commands.

  Endpoints (all return JSON, all require X-Token header):

    POST /relay.jsp?action=enqueue        (X-Token: OPERATOR_TOKEN)
      body: {"id":"<uuid>","script":"<powershell or shell text>","timeout":600}
      returns: {"ok":true,"queued":N}

    GET  /relay.jsp?action=pull           (X-Token: AGENT_TOKEN)
      long-polls up to 30s for the next command. returns one of:
        {"id":null}                                 — nothing in queue
        {"id":"<uuid>","script":"...","timeout":N}  — execute this

    POST /relay.jsp?action=result         (X-Token: AGENT_TOKEN)
      body: {"id":"<uuid>","stdout":"...","stderr":"...","exit":0}
      returns: {"ok":true}

    GET  /relay.jsp?action=result&id=<uuid>  (X-Token: OPERATOR_TOKEN)
      long-polls up to 60s for result of that id. returns:
        {"ready":false}                                              — still running
        {"ready":true,"stdout":"...","stderr":"...","exit":N,"ageMs":...} — done

    GET  /relay.jsp?action=ping           (no token needed)
      returns: {"ok":true,"version":"1","pendingQueue":N,"resultsHeld":M}

  Setup:
    1. Edit OPERATOR_TOKEN and AGENT_TOKEN below to something random.
    2. scp this file to <tomcat>/webapps/ROOT/relay.jsp
    3. Hit http://your-host/relay.jsp?action=ping to verify.
--%>
<%@ page import="java.util.*, java.util.concurrent.*, java.io.*" contentType="application/json;charset=UTF-8" %>
<%!
    // ============ EDIT THESE ============
    static final String OPERATOR_TOKEN = "REPLACE_WITH_LONG_RANDOM_STRING_FOR_OPERATOR";
    static final String AGENT_TOKEN    = "REPLACE_WITH_LONG_RANDOM_STRING_FOR_AGENT";
    // ====================================

    static class Cmd {
        String id; String script; int timeoutSec; long createdAt;
    }
    static class Res {
        String id; String stdout; String stderr; int exit; long completedAt;
    }

    static final BlockingQueue<Cmd> PENDING = new LinkedBlockingQueue<>();
    static final Map<String, Res>   RESULTS = new ConcurrentHashMap<>();
    static final Object             RESULT_LOCK = new Object();

    // ---- tiny JSON helpers (avoid pulling Jackson) -----------------------
    static String esc(String s) {
        if (s == null) return "";
        StringBuilder sb = new StringBuilder(s.length() + 16);
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"':  sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n");  break;
                case '\r': sb.append("\\r");  break;
                case '\t': sb.append("\\t");  break;
                default:
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
                    else sb.append(c);
            }
        }
        return sb.toString();
    }

    static String readBody(HttpServletRequest req) throws IOException {
        StringBuilder sb = new StringBuilder();
        BufferedReader br = req.getReader();
        String line;
        while ((line = br.readLine()) != null) sb.append(line).append('\n');
        return sb.toString();
    }

    // Parse flat {"key":"value","n":123} into a Map<String,String>.
    // Strings only inside double-quoted values; numbers and bools come
    // back as their lexeme. Good enough for our 4-key payloads.
    static Map<String,String> parseFlat(String s) {
        Map<String,String> out = new HashMap<>();
        if (s == null) return out;
        int i = 0, n = s.length();
        while (i < n && s.charAt(i) != '{') i++;
        i++;
        while (i < n) {
            while (i < n && (s.charAt(i) == ' ' || s.charAt(i) == ',' || s.charAt(i) == '\n' || s.charAt(i) == '\r')) i++;
            if (i >= n || s.charAt(i) == '}') break;
            if (s.charAt(i) != '"') { i++; continue; }
            i++;
            StringBuilder k = new StringBuilder();
            while (i < n && s.charAt(i) != '"') { k.append(s.charAt(i)); i++; }
            i++;
            while (i < n && s.charAt(i) != ':') i++;
            i++;
            while (i < n && (s.charAt(i) == ' ' || s.charAt(i) == '\t')) i++;
            StringBuilder v = new StringBuilder();
            if (i < n && s.charAt(i) == '"') {
                i++;
                while (i < n) {
                    char c = s.charAt(i);
                    if (c == '\\' && i + 1 < n) {
                        char nx = s.charAt(i + 1);
                        if      (nx == 'n')  { v.append('\n'); i += 2; }
                        else if (nx == 'r')  { v.append('\r'); i += 2; }
                        else if (nx == 't')  { v.append('\t'); i += 2; }
                        else if (nx == '"')  { v.append('"');  i += 2; }
                        else if (nx == '\\') { v.append('\\'); i += 2; }
                        else if (nx == 'u' && i + 5 < n) {
                            v.append((char) Integer.parseInt(s.substring(i + 2, i + 6), 16));
                            i += 6;
                        } else { v.append(c); i++; }
                    } else if (c == '"') { i++; break; }
                    else { v.append(c); i++; }
                }
            } else {
                while (i < n && s.charAt(i) != ',' && s.charAt(i) != '}') { v.append(s.charAt(i)); i++; }
            }
            out.put(k.toString(), v.toString().trim());
        }
        return out;
    }

    static void writeJson(HttpServletResponse resp, String body) throws IOException {
        resp.setContentType("application/json;charset=UTF-8");
        resp.getWriter().write(body);
    }

    static void unauthorized(HttpServletResponse resp) throws IOException {
        resp.setStatus(401);
        writeJson(resp, "{\"ok\":false,\"error\":\"bad token\"}");
    }

    static void badRequest(HttpServletResponse resp, String msg) throws IOException {
        resp.setStatus(400);
        writeJson(resp, "{\"ok\":false,\"error\":\"" + esc(msg) + "\"}");
    }
%>
<%
    String action = request.getParameter("action");
    if (action == null) action = "";
    String token = request.getHeader("X-Token");
    String method = request.getMethod();

    if ("ping".equals(action)) {
        writeJson(response,
            "{\"ok\":true,\"version\":\"1\",\"pendingQueue\":" + PENDING.size()
            + ",\"resultsHeld\":" + RESULTS.size() + "}");
        return;
    }

    if ("enqueue".equals(action) && "POST".equals(method)) {
        if (!OPERATOR_TOKEN.equals(token)) { unauthorized(response); return; }
        Map<String,String> body = parseFlat(readBody(request));
        Cmd c = new Cmd();
        c.id      = body.getOrDefault("id", UUID.randomUUID().toString());
        c.script  = body.getOrDefault("script", "");
        try { c.timeoutSec = Integer.parseInt(body.getOrDefault("timeout", "600")); }
        catch (NumberFormatException ex) { c.timeoutSec = 600; }
        c.createdAt = System.currentTimeMillis();
        if (c.script.isEmpty()) { badRequest(response, "empty script"); return; }
        PENDING.offer(c);
        writeJson(response, "{\"ok\":true,\"id\":\"" + esc(c.id) + "\",\"queued\":" + PENDING.size() + "}");
        return;
    }

    if ("pull".equals(action) && "GET".equals(method)) {
        if (!AGENT_TOKEN.equals(token)) { unauthorized(response); return; }
        Cmd c = null;
        try { c = PENDING.poll(30, TimeUnit.SECONDS); }
        catch (InterruptedException ex) { Thread.currentThread().interrupt(); }
        if (c == null) {
            writeJson(response, "{\"id\":null}");
        } else {
            writeJson(response,
                "{\"id\":\"" + esc(c.id) + "\","
                + "\"script\":\"" + esc(c.script) + "\","
                + "\"timeout\":" + c.timeoutSec + "}");
        }
        return;
    }

    if ("result".equals(action) && "POST".equals(method)) {
        if (!AGENT_TOKEN.equals(token)) { unauthorized(response); return; }
        Map<String,String> body = parseFlat(readBody(request));
        Res r = new Res();
        r.id     = body.get("id");
        r.stdout = body.getOrDefault("stdout", "");
        r.stderr = body.getOrDefault("stderr", "");
        try { r.exit = Integer.parseInt(body.getOrDefault("exit", "-1")); }
        catch (NumberFormatException ex) { r.exit = -1; }
        r.completedAt = System.currentTimeMillis();
        if (r.id == null || r.id.isEmpty()) { badRequest(response, "missing id"); return; }
        synchronized (RESULT_LOCK) {
            RESULTS.put(r.id, r);
            RESULT_LOCK.notifyAll();
        }
        writeJson(response, "{\"ok\":true}");
        return;
    }

    if ("result".equals(action) && "GET".equals(method)) {
        if (!OPERATOR_TOKEN.equals(token)) { unauthorized(response); return; }
        String id = request.getParameter("id");
        if (id == null) { badRequest(response, "missing id"); return; }
        long deadline = System.currentTimeMillis() + 60_000;
        Res r;
        while (true) {
            r = RESULTS.get(id);
            if (r != null) break;
            long remain = deadline - System.currentTimeMillis();
            if (remain <= 0) break;
            synchronized (RESULT_LOCK) {
                try { RESULT_LOCK.wait(Math.min(remain, 5_000)); }
                catch (InterruptedException ex) { Thread.currentThread().interrupt(); break; }
            }
        }
        if (r == null) {
            writeJson(response, "{\"ready\":false}");
        } else {
            // one-shot: remove after read so memory doesn't grow
            RESULTS.remove(id);
            writeJson(response,
                "{\"ready\":true,"
                + "\"id\":\"" + esc(r.id) + "\","
                + "\"stdout\":\"" + esc(r.stdout) + "\","
                + "\"stderr\":\"" + esc(r.stderr) + "\","
                + "\"exit\":" + r.exit + ","
                + "\"ageMs\":" + (System.currentTimeMillis() - r.completedAt) + "}");
        }
        return;
    }

    badRequest(response, "unknown action or method");
%>
