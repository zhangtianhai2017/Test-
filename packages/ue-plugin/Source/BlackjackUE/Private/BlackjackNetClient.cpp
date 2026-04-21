#include "BlackjackNetClient.h"

#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "TimerManager.h"
#include "WebSocketsModule.h"
#include "IWebSocket.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Modules/ModuleManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogBlackjackNet, Log, All);

namespace
{
    const TCHAR* const kClientVersion = TEXT("ue-0.1.0");
}

void UBlackjackNetClient::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);

    // Make sure the WebSockets module is loaded before we try to create sockets.
    // It's safe to call LoadModuleChecked even if the module was already loaded.
    FModuleManager::Get().LoadModuleChecked(TEXT("WebSockets"));

    State = EBlackjackConnectionState::Disconnected;
    SessionId.Reset();
    DisplayName.Reset();
    PendingResumeSessionId.Reset();
    ReconnectGraceSeconds = 0;
}

void UBlackjackNetClient::Deinitialize()
{
    StopPingTimer();
    ReleaseSocket();
    Super::Deinitialize();
}

void UBlackjackNetClient::Connect(const FString& Host, int32 Port, const FString& InDisplayName)
{
    // If we're already connected (or mid-connection), close first so we start clean.
    if (Socket.IsValid())
    {
        Disconnect();
    }

    DisplayName = InDisplayName;

    // If we have a lingering session from a prior connection, try to resume it.
    if (!SessionId.IsEmpty())
    {
        PendingResumeSessionId = SessionId;
    }
    else
    {
        PendingResumeSessionId.Reset();
    }

    const FString Url = FString::Printf(TEXT("ws://%s:%d/game"), *Host, Port);
    UE_LOG(LogBlackjackNet, Log, TEXT("Connecting to %s as '%s'%s"),
        *Url,
        *DisplayName,
        PendingResumeSessionId.IsEmpty() ? TEXT("") : TEXT(" (resume)"));

    Socket = FWebSocketsModule::Get().CreateWebSocket(Url);
    if (!Socket.IsValid())
    {
        UE_LOG(LogBlackjackNet, Error, TEXT("CreateWebSocket returned null for %s"), *Url);
        SetState(EBlackjackConnectionState::Disconnected);
        return;
    }

    Socket->OnConnected().AddUObject(this, &UBlackjackNetClient::HandleConnected);
    Socket->OnConnectionError().AddUObject(this, &UBlackjackNetClient::HandleConnectionError);
    Socket->OnClosed().AddUObject(this, &UBlackjackNetClient::HandleClosed);
    Socket->OnMessage().AddUObject(this, &UBlackjackNetClient::HandleMessage);

    SetState(EBlackjackConnectionState::Connecting);
    Socket->Connect();
}

void UBlackjackNetClient::Disconnect()
{
    StopPingTimer();

    if (Socket.IsValid())
    {
        if (Socket->IsConnected())
        {
            Socket->Close();
        }
    }
    ReleaseSocket();

    // Note: we intentionally keep SessionId around so a follow-up Connect()
    // can resume within the server's grace window (D-022).
    SetState(EBlackjackConnectionState::Disconnected);
}

void UBlackjackNetClient::ReleaseSocket()
{
    if (Socket.IsValid())
    {
        Socket->OnConnected().RemoveAll(this);
        Socket->OnConnectionError().RemoveAll(this);
        Socket->OnClosed().RemoveAll(this);
        Socket->OnMessage().RemoveAll(this);
        Socket.Reset();
    }
}

void UBlackjackNetClient::SetState(EBlackjackConnectionState NewState)
{
    if (State == NewState)
    {
        return;
    }
    State = NewState;
    OnConnectionStateChanged.Broadcast(State);
}

void UBlackjackNetClient::HandleConnected()
{
    UE_LOG(LogBlackjackNet, Log, TEXT("WebSocket connected; sending HELLO."));
    SetState(EBlackjackConnectionState::Awaiting_Hello);
    SendHello();
}

void UBlackjackNetClient::HandleConnectionError(const FString& Error)
{
    UE_LOG(LogBlackjackNet, Warning, TEXT("WebSocket connection error: %s"), *Error);
    StopPingTimer();
    ReleaseSocket();
    SetState(EBlackjackConnectionState::Disconnected);
}

void UBlackjackNetClient::HandleClosed(int32 StatusCode, const FString& Reason, bool bWasClean)
{
    UE_LOG(LogBlackjackNet, Log, TEXT("WebSocket closed: code=%d reason='%s' clean=%s"),
        StatusCode, *Reason, bWasClean ? TEXT("true") : TEXT("false"));

    StopPingTimer();
    ReleaseSocket();

    // If we had a session, the server is holding our seats for `ReconnectGraceSeconds`.
    // Report `Closed` so callers know the session is still recoverable via a new Connect().
    if (!SessionId.IsEmpty())
    {
        SetState(EBlackjackConnectionState::Closed);
    }
    else
    {
        SetState(EBlackjackConnectionState::Disconnected);
    }
}

void UBlackjackNetClient::SendHello()
{
    const TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetNumberField(TEXT("v"), static_cast<double>(PROTOCOL_VERSION));
    Obj->SetStringField(TEXT("type"), TEXT("HELLO"));
    Obj->SetStringField(TEXT("displayName"), DisplayName);
    Obj->SetStringField(TEXT("clientVersion"), kClientVersion);
    if (!PendingResumeSessionId.IsEmpty())
    {
        Obj->SetStringField(TEXT("resumeSessionId"), PendingResumeSessionId);
    }

    FString Out;
    const TSharedRef<TJsonWriter<TCHAR>> Writer =
        TJsonWriterFactory<TCHAR>::Create(&Out);
    FJsonSerializer::Serialize(Obj, Writer);

    SendFrame(Out);
}

void UBlackjackNetClient::SendPing()
{
    if (State != EBlackjackConnectionState::Connected)
    {
        return;
    }
    if (!Socket.IsValid() || !Socket->IsConnected())
    {
        return;
    }

    const int64 NowMs = FDateTime::UtcNow().ToUnixTimestamp() * 1000
        + static_cast<int64>(FDateTime::UtcNow().GetMillisecond());

    const TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetNumberField(TEXT("v"), static_cast<double>(PROTOCOL_VERSION));
    Obj->SetStringField(TEXT("type"), TEXT("PING"));
    Obj->SetNumberField(TEXT("timestamp"), static_cast<double>(NowMs));

    FString Out;
    const TSharedRef<TJsonWriter<TCHAR>> Writer =
        TJsonWriterFactory<TCHAR>::Create(&Out);
    FJsonSerializer::Serialize(Obj, Writer);

    SendFrame(Out);
}

void UBlackjackNetClient::StartPingTimer()
{
    StopPingTimer();

    UWorld* World = nullptr;
    if (UGameInstance* GI = GetGameInstance())
    {
        World = GI->GetWorld();
    }
    if (!World)
    {
        UE_LOG(LogBlackjackNet, Warning, TEXT("Cannot start ping timer: no world available."));
        return;
    }

    World->GetTimerManager().SetTimer(
        PingTimerHandle,
        this,
        &UBlackjackNetClient::SendPing,
        PingIntervalSeconds,
        /*bLoop=*/ true);
}

void UBlackjackNetClient::StopPingTimer()
{
    if (!PingTimerHandle.IsValid())
    {
        return;
    }

    UWorld* World = nullptr;
    if (UGameInstance* GI = GetGameInstance())
    {
        World = GI->GetWorld();
    }
    if (World)
    {
        World->GetTimerManager().ClearTimer(PingTimerHandle);
    }
    PingTimerHandle.Invalidate();
}

void UBlackjackNetClient::SendFrame(const FString& JsonStr)
{
    if (!Socket.IsValid() || !Socket->IsConnected())
    {
        UE_LOG(LogBlackjackNet, Warning, TEXT("SendFrame called with no open socket; dropping: %s"), *JsonStr);
        return;
    }
    Socket->Send(JsonStr);
}

void UBlackjackNetClient::HandleMessage(const FString& Message)
{
    TSharedPtr<FJsonObject> Obj;
    const TSharedRef<TJsonReader<TCHAR>> Reader = TJsonReaderFactory<TCHAR>::Create(Message);
    if (!FJsonSerializer::Deserialize(Reader, Obj) || !Obj.IsValid())
    {
        UE_LOG(LogBlackjackNet, Warning, TEXT("Failed to parse incoming frame: %s"), *Message);
        return;
    }

    DispatchFrame(Obj);
}

void UBlackjackNetClient::DispatchFrame(const TSharedPtr<FJsonObject>& Frame)
{
    if (!Frame.IsValid())
    {
        return;
    }

    // Validate protocol version first. We accept only the exact literal.
    double Version = 0.0;
    if (!Frame->TryGetNumberField(TEXT("v"), Version) ||
        static_cast<int32>(Version) != PROTOCOL_VERSION)
    {
        const FString Msg = FString::Printf(
            TEXT("Server frame has unsupported protocol version: %.0f (expected %d)"),
            Version, PROTOCOL_VERSION);
        UE_LOG(LogBlackjackNet, Error, TEXT("%s"), *Msg);
        OnServerError.Broadcast(TEXT("BAD_VERSION"), Msg);
        return;
    }

    FString Type;
    if (!Frame->TryGetStringField(TEXT("type"), Type))
    {
        UE_LOG(LogBlackjackNet, Warning, TEXT("Frame missing 'type' field; ignoring."));
        return;
    }

    if (Type == TEXT("WELCOME"))
    {
        FString NewSessionId;
        Frame->TryGetStringField(TEXT("sessionId"), NewSessionId);

        int32 Grace = 0;
        Frame->TryGetNumberField(TEXT("reconnectGraceSeconds"), Grace);

        SessionId = NewSessionId;
        ReconnectGraceSeconds = Grace;
        PendingResumeSessionId.Reset();

        UE_LOG(LogBlackjackNet, Log, TEXT("WELCOME sessionId=%s grace=%ds"), *SessionId, Grace);

        SetState(EBlackjackConnectionState::Connected);
        OnWelcome.Broadcast(SessionId, Grace);
        StartPingTimer();
        return;
    }

    if (Type == TEXT("PONG"))
    {
        // Keep-alive echo; nothing to do in M5a.
        return;
    }

    if (Type == TEXT("ERROR"))
    {
        FString Code;
        FString Msg;
        Frame->TryGetStringField(TEXT("code"), Code);
        Frame->TryGetStringField(TEXT("message"), Msg);
        UE_LOG(LogBlackjackNet, Warning, TEXT("Server ERROR %s: %s"), *Code, *Msg);
        OnServerError.Broadcast(Code, Msg);
        return;
    }

    // M5b will route: TABLE_STATE, CARD_DEALT, PHASE_CHANGED, SEAT_ASSIGNED,
    // HOLE_CARD_REVEALED, ROUND_OVER, BANKROLL_CHANGED, DEALER_QUIP, etc.
    UE_LOG(LogBlackjackNet, Verbose, TEXT("Frame not handled in M5a: %s"), *Type);
}
