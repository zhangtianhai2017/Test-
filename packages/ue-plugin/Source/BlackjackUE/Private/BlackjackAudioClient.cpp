#include "BlackjackAudioClient.h"

#include "Engine/World.h"
#include "HttpModule.h"
#include "Interfaces/IHttpResponse.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundWaveProcedural.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

DEFINE_LOG_CATEGORY_STATIC(LogBlackjackAudio, Log, All);

// ---------------------------------------------------------------------------
// Subsystem lifecycle
// ---------------------------------------------------------------------------

void UBlackjackAudioClient::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    // We intentionally skip a periodic /health pinger; bTtsReady is latched
    // optimistically on the first 2xx TTS response, and cleared on 503.
    // Callers that care may invoke RefreshReadyFromHealth() explicitly.
}

void UBlackjackAudioClient::Deinitialize()
{
    // Outstanding HTTP requests: FHttpModule's manager keeps weak refs to the
    // completion lambda so letting them lapse is safe — but we null our
    // state here to make post-shutdown callbacks no-ops.
    BaseUrl.Reset();
    SessionId.Reset();
    bTtsReady = false;
    VoiceByLanguage.Empty();
    Super::Deinitialize();
}

// ---------------------------------------------------------------------------
// Configuration setters
// ---------------------------------------------------------------------------

void UBlackjackAudioClient::SetBaseUrl(const FString& Url)
{
    // Strip a trailing slash so we can always concatenate with `/session/...`.
    FString Trimmed = Url;
    while (Trimmed.EndsWith(TEXT("/")))
    {
        Trimmed.LeftChopInline(1);
    }
    BaseUrl = MoveTemp(Trimmed);
}

void UBlackjackAudioClient::SetSessionId(const FString& Id)
{
    SessionId = Id;
}

void UBlackjackAudioClient::SetVoiceForLanguage(const FString& Language, const FString& VoiceId)
{
    if (Language.IsEmpty())
    {
        return;
    }
    if (VoiceId.IsEmpty())
    {
        VoiceByLanguage.Remove(Language);
    }
    else
    {
        VoiceByLanguage.Add(Language, VoiceId);
    }
}

// ---------------------------------------------------------------------------
// Public speak entry points
// ---------------------------------------------------------------------------

void UBlackjackAudioClient::SpeakQuip(const FString& Text, const FString& VoiceId)
{
    if (BaseUrl.IsEmpty() || SessionId.IsEmpty())
    {
        UE_LOG(LogBlackjackAudio, Warning, TEXT("SpeakQuip: not configured (BaseUrl or SessionId empty)"));
        OnQuipAudioError.Broadcast(TEXT("not-configured"));
        return;
    }
    if (Text.IsEmpty())
    {
        OnQuipAudioError.Broadcast(TEXT("empty-text"));
        return;
    }
    DoRequestQuipTts(Text, VoiceId);
}

void UBlackjackAudioClient::HandleDealerQuip(const FString& Text, const FString& Tone, const FString& Language, const FString& AudioUrl)
{
    // Tone is currently informational only; Blueprints may read it from the
    // NetClient delegate directly if they want tone-specific animation.
    (void)Tone;

    if (!AudioUrl.IsEmpty())
    {
        // Server already rendered audio and published a URL — direct GET.
        DoRequestUrl(AudioUrl);
        return;
    }

    // Otherwise request fresh TTS for the quip text. Use an explicit override
    // if the caller registered one for this language; else pass "" and let
    // dealer-ai pick the persona's default voice.
    const FString* Override = VoiceByLanguage.Find(Language);
    SpeakQuip(Text, Override ? *Override : FString());
}

// ---------------------------------------------------------------------------
// HTTP plumbing
// ---------------------------------------------------------------------------

FString UBlackjackAudioClient::EscapeJsonString(const FString& In)
{
    // Minimal JSON string escaper. We only see dealer quip text, which is
    // plain-language user content — `\` and `"` are the realistic hazards
    // but we also escape control chars per RFC 8259 to be safe.
    FString Out;
    Out.Reserve(In.Len() + 8);
    for (TCHAR Ch : In)
    {
        switch (Ch)
        {
            case TEXT('\\'): Out.Append(TEXT("\\\\")); break;
            case TEXT('"'):  Out.Append(TEXT("\\\"")); break;
            case TEXT('\b'): Out.Append(TEXT("\\b"));  break;
            case TEXT('\f'): Out.Append(TEXT("\\f"));  break;
            case TEXT('\n'): Out.Append(TEXT("\\n"));  break;
            case TEXT('\r'): Out.Append(TEXT("\\r"));  break;
            case TEXT('\t'): Out.Append(TEXT("\\t"));  break;
            default:
                if (Ch < 0x20)
                {
                    Out.Append(FString::Printf(TEXT("\\u%04x"), static_cast<int32>(Ch)));
                }
                else
                {
                    Out.AppendChar(Ch);
                }
                break;
        }
    }
    return Out;
}

void UBlackjackAudioClient::DoRequestQuipTts(const FString& Text, const FString& VoiceId)
{
    const FString Url = FString::Printf(TEXT("%s/session/%s/tts"), *BaseUrl, *SessionId);

    // Hand-build the JSON body — the payload is trivial and avoids importing
    // JsonUtilities for a single-field struct. Matches dealer_ai.schema.TTSRequest.
    FString Body;
    if (VoiceId.IsEmpty())
    {
        Body = FString::Printf(TEXT("{\"text\":\"%s\"}"), *EscapeJsonString(Text));
    }
    else
    {
        Body = FString::Printf(
            TEXT("{\"text\":\"%s\",\"voice_id\":\"%s\"}"),
            *EscapeJsonString(Text),
            *EscapeJsonString(VoiceId));
    }

    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req = FHttpModule::Get().CreateRequest();
    Req->SetURL(Url);
    Req->SetVerb(TEXT("POST"));
    Req->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
    Req->SetHeader(TEXT("Accept"), TEXT("audio/wav"));
    Req->SetContentAsString(Body);
    Req->OnProcessRequestComplete().BindUObject(this, &UBlackjackAudioClient::OnTtsResponse);
    if (!Req->ProcessRequest())
    {
        OnQuipAudioError.Broadcast(TEXT("network"));
    }
}

void UBlackjackAudioClient::DoRequestUrl(const FString& Url)
{
    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req = FHttpModule::Get().CreateRequest();
    Req->SetURL(Url);
    Req->SetVerb(TEXT("GET"));
    Req->SetHeader(TEXT("Accept"), TEXT("audio/wav"));
    Req->OnProcessRequestComplete().BindUObject(this, &UBlackjackAudioClient::OnUrlResponse);
    if (!Req->ProcessRequest())
    {
        OnQuipAudioError.Broadcast(TEXT("network"));
    }
}

void UBlackjackAudioClient::OnTtsResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bSuccess)
{
    if (!bSuccess || !Response.IsValid())
    {
        OnQuipAudioError.Broadcast(TEXT("network"));
        return;
    }

    const int32 Code = Response->GetResponseCode();
    if (Code == 503)
    {
        // dealer-ai returns `{"ready": false, "status": "..."}` when TTS is
        // unavailable (CPU-only sandbox, missing weights, disabled by env).
        bTtsReady = false;
        const FString BodyStr = Response->GetContentAsString();
        FString Status = TEXT("tts-unavailable");
        TSharedPtr<FJsonObject> Obj;
        TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(BodyStr);
        if (FJsonSerializer::Deserialize(Reader, Obj) && Obj.IsValid())
        {
            FString ParsedStatus;
            if (Obj->TryGetStringField(TEXT("status"), ParsedStatus) && !ParsedStatus.IsEmpty())
            {
                Status = ParsedStatus;
            }
        }
        OnQuipAudioError.Broadcast(Status);
        return;
    }

    if (Code < 200 || Code >= 300)
    {
        OnQuipAudioError.Broadcast(FString::Printf(TEXT("http-%d"), Code));
        return;
    }

    const TArray<uint8>& Bytes = Response->GetContent();
    if (Bytes.Num() == 0)
    {
        OnQuipAudioError.Broadcast(TEXT("empty-response"));
        return;
    }

    // Latch ready once the server has successfully served audio to us.
    bTtsReady = true;
    PlayWavBytes(Bytes);
}

void UBlackjackAudioClient::OnUrlResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bSuccess)
{
    if (!bSuccess || !Response.IsValid())
    {
        OnQuipAudioError.Broadcast(TEXT("network"));
        return;
    }
    const int32 Code = Response->GetResponseCode();
    if (Code < 200 || Code >= 300)
    {
        OnQuipAudioError.Broadcast(FString::Printf(TEXT("http-%d"), Code));
        return;
    }
    const TArray<uint8>& Bytes = Response->GetContent();
    if (Bytes.Num() == 0)
    {
        OnQuipAudioError.Broadcast(TEXT("empty-response"));
        return;
    }
    PlayWavBytes(Bytes);
}

// ---------------------------------------------------------------------------
// WAV decoding
// ---------------------------------------------------------------------------

namespace
{
    // Tiny helpers for little-endian field reads. The WAV header is always LE.
    FORCEINLINE uint16 ReadU16LE(const uint8* P)
    {
        return static_cast<uint16>(P[0]) | (static_cast<uint16>(P[1]) << 8);
    }
    FORCEINLINE uint32 ReadU32LE(const uint8* P)
    {
        return  static_cast<uint32>(P[0])
              | (static_cast<uint32>(P[1]) << 8)
              | (static_cast<uint32>(P[2]) << 16)
              | (static_cast<uint32>(P[3]) << 24);
    }
}

void UBlackjackAudioClient::PlayWavBytes(const TArray<uint8>& WavBytes)
{
    // CosyVoice (M10) defaults: 16-bit PCM mono @ 22050 Hz. We still parse
    // the header so we degrade gracefully if the service ever swaps codec.
    uint32 SampleRate = 22050;
    uint16 NumChannels = 1;
    uint16 BitsPerSample = 16;
    int32 DataOffset = 44;   // Standard RIFF/WAVE/fmt /data layout
    int32 DataSize = WavBytes.Num() - 44;

    auto ReportBadAudio = [&](const TCHAR* Why)
    {
        UE_LOG(LogBlackjackAudio, Warning, TEXT("PlayWavBytes: %s"), Why);
        OnQuipAudioError.Broadcast(TEXT("bad-audio"));
    };

    // Best-effort header scan. We don't abort on mismatch — we log and try
    // to play anyway so a malformed header doesn't silence the dealer.
    if (WavBytes.Num() >= 44
        && WavBytes[0] == 'R' && WavBytes[1] == 'I' && WavBytes[2] == 'F' && WavBytes[3] == 'F'
        && WavBytes[8] == 'W' && WavBytes[9] == 'A' && WavBytes[10] == 'V' && WavBytes[11] == 'E')
    {
        // Walk the chunk list to find `fmt ` and `data`. This handles files
        // that have a JUNK/LIST/bext chunk before `data` (some encoders emit
        // extra metadata; CosyVoice typically doesn't, but we're defensive).
        int32 Cursor = 12;
        bool bFoundFmt = false;
        bool bFoundData = false;
        while (Cursor + 8 <= WavBytes.Num() && !(bFoundFmt && bFoundData))
        {
            const uint8* ChunkId = &WavBytes[Cursor];
            const uint32 ChunkSize = ReadU32LE(&WavBytes[Cursor + 4]);
            const int32 ChunkBody = Cursor + 8;
            if (!bFoundFmt
                && ChunkId[0] == 'f' && ChunkId[1] == 'm' && ChunkId[2] == 't' && ChunkId[3] == ' '
                && ChunkBody + 16 <= WavBytes.Num())
            {
                // fmt chunk: AudioFormat(2) Channels(2) SampleRate(4) ByteRate(4) BlockAlign(2) BitsPerSample(2)
                NumChannels  = ReadU16LE(&WavBytes[ChunkBody + 2]);
                SampleRate   = ReadU32LE(&WavBytes[ChunkBody + 4]);
                BitsPerSample = ReadU16LE(&WavBytes[ChunkBody + 14]);
                bFoundFmt = true;
            }
            else if (!bFoundData
                && ChunkId[0] == 'd' && ChunkId[1] == 'a' && ChunkId[2] == 't' && ChunkId[3] == 'a')
            {
                DataOffset = ChunkBody;
                DataSize = FMath::Min<int32>(static_cast<int32>(ChunkSize), WavBytes.Num() - ChunkBody);
                bFoundData = true;
            }
            // Chunks are word-aligned — round size up to even.
            Cursor = ChunkBody + static_cast<int32>(ChunkSize) + (static_cast<int32>(ChunkSize) & 1);
        }
        if (!bFoundData)
        {
            ReportBadAudio(TEXT("no data chunk"));
            return;
        }
    }
    else
    {
        // No RIFF header at all — we can't reliably play this.
        ReportBadAudio(TEXT("not a RIFF/WAVE file"));
        return;
    }

    if (BitsPerSample != 16 || NumChannels == 0 || SampleRate == 0 || DataSize <= 0)
    {
        UE_LOG(LogBlackjackAudio, Warning,
               TEXT("PlayWavBytes: unexpected format (bps=%u ch=%u sr=%u data=%d) -- attempting playback anyway"),
               BitsPerSample, NumChannels, SampleRate, DataSize);
    }

    // Build a procedural wave and queue the PCM. Construct with `this` as the
    // outer so the UObject lives at least as long as the subsystem; the
    // engine's audio device retains its own ref while it's actively playing.
    USoundWaveProcedural* Wave = NewObject<USoundWaveProcedural>(this);
    if (!Wave)
    {
        ReportBadAudio(TEXT("failed to create USoundWaveProcedural"));
        return;
    }
    Wave->SetSampleRate(SampleRate);
    Wave->NumChannels = NumChannels;
    Wave->Duration = INDEFINITELY_LOOPING_DURATION;  // procedural — unknown upfront
    Wave->SoundGroup = SOUNDGROUP_Voice;
    Wave->bLooping = false;

    // Queue the raw PCM bytes (already little-endian 16-bit, which matches
    // USoundWaveProcedural's expected format).
    TArray<uint8> Pcm;
    Pcm.Append(WavBytes.GetData() + DataOffset, DataSize);
    Wave->QueueAudio(Pcm.GetData(), Pcm.Num());

    OnQuipAudioReady.Broadcast(Wave);

    UWorld* World = GetWorld();
    if (World)
    {
        UGameplayStatics::PlaySound2D(World, Wave, VolumeMultiplier);
    }
    else
    {
        // No world yet (very early init). Still a success from the fetch's
        // perspective — the OnQuipAudioReady listener may attach it to an
        // AudioComponent themselves.
        UE_LOG(LogBlackjackAudio, Verbose, TEXT("PlayWavBytes: no world; skipping PlaySound2D"));
    }
}

// ---------------------------------------------------------------------------
// Optional /health polling (invoked manually; no timer wired up in Initialize)
// ---------------------------------------------------------------------------

void UBlackjackAudioClient::RefreshReadyFromHealth()
{
    if (BaseUrl.IsEmpty())
    {
        return;
    }
    const FString Url = FString::Printf(TEXT("%s/health"), *BaseUrl);
    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req = FHttpModule::Get().CreateRequest();
    Req->SetURL(Url);
    Req->SetVerb(TEXT("GET"));
    Req->SetHeader(TEXT("Accept"), TEXT("application/json"));
    Req->OnProcessRequestComplete().BindUObject(this, &UBlackjackAudioClient::OnHealthResponse);
    Req->ProcessRequest();
}

void UBlackjackAudioClient::OnHealthResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bSuccess)
{
    if (!bSuccess || !Response.IsValid() || Response->GetResponseCode() != 200)
    {
        return;
    }
    const FString BodyStr = Response->GetContentAsString();
    TSharedPtr<FJsonObject> Obj;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(BodyStr);
    if (!FJsonSerializer::Deserialize(Reader, Obj) || !Obj.IsValid())
    {
        return;
    }
    // Response shape (schema.HealthResponse): `tts: { ready: bool, status: str }`.
    const TSharedPtr<FJsonObject>* Tts = nullptr;
    if (Obj->TryGetObjectField(TEXT("tts"), Tts) && Tts && Tts->IsValid())
    {
        bool bReady = false;
        if ((*Tts)->TryGetBoolField(TEXT("ready"), bReady))
        {
            bTtsReady = bReady;
        }
    }
}
