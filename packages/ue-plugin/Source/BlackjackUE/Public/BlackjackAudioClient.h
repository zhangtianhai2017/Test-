#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Interfaces/IHttpRequest.h"
#include "BlackjackAudioClient.generated.h"

class USoundWave;
class USoundWaveProcedural;

/**
 * Blueprint-assignable delegates for audio fetch lifecycle.
 *
 * OnQuipAudioReady fires *after* the WAV has been decoded into a
 * USoundWave(Procedural) but *before* PlaySound2D is invoked, giving
 * Blueprint graphs a chance to route it to a 3D AudioComponent attached
 * to the dealer character rather than playing it as 2D UI audio.
 *
 * OnQuipAudioError fires on any failure path (not-configured, network,
 * 503 with status string from dealer-ai, empty body, malformed WAV, etc.).
 */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnQuipAudioReady, USoundWave*, SoundWave);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnQuipAudioError, const FString&, Reason);

/**
 * Game-instance subsystem that fetches dealer TTS audio from the
 * `dealer-ai` Python HTTP service and plays it back in UE.
 *
 * Pairs with UBlackjackNetClient::OnDealerQuip — connect the multicast
 * delegate in Blueprint (or C++) to HandleDealerQuip and it will pull
 * the WAV bytes from `/session/<sid>/tts` and PlaySound2D them.
 */
UCLASS()
class BLACKJACKUE_API UBlackjackAudioClient : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

    /** Set the base URL of the dealer-ai HTTP service, e.g. http://127.0.0.1:8787. */
    UFUNCTION(BlueprintCallable, Category = "Blackjack|Audio")
    void SetBaseUrl(const FString& Url);

    /** Set the dealer-ai session id (returned by the Python service on /session). */
    UFUNCTION(BlueprintCallable, Category = "Blackjack|Audio")
    void SetSessionId(const FString& Id);

    /** True when the audio client believes the TTS endpoint is available. */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "Blackjack|Audio")
    bool IsTtsReady() const { return bTtsReady; }

    /** Fetch + play a TTS quip. Called from Blueprint or by hookup to OnDealerQuip. */
    UFUNCTION(BlueprintCallable, Category = "Blackjack|Audio")
    void SpeakQuip(const FString& Text, const FString& VoiceId);

    /** Convenience: plug this straight into UBlackjackNetClient::OnDealerQuip. */
    UFUNCTION(BlueprintCallable, Category = "Blackjack|Audio")
    void HandleDealerQuip(const FString& Text, const FString& Tone, const FString& Language, const FString& AudioUrl);

    /** Override default voice for a language. Language is "zh" or "en". */
    UFUNCTION(BlueprintCallable, Category = "Blackjack|Audio")
    void SetVoiceForLanguage(const FString& Language, const FString& VoiceId);

    /** Fired once the downloaded quip has been decoded into a SoundWave (pre-play). */
    UPROPERTY(BlueprintAssignable, Category = "Blackjack|Audio")
    FOnQuipAudioReady OnQuipAudioReady;

    /** Fired when a quip fails for any reason (network, 503, bad-audio, not-configured). */
    UPROPERTY(BlueprintAssignable, Category = "Blackjack|Audio")
    FOnQuipAudioError OnQuipAudioError;

    /** Linear volume multiplier passed to UGameplayStatics::PlaySound2D. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Audio")
    float VolumeMultiplier = 1.f;

protected:
    /** Dealer-ai HTTP base URL. Default matches `dealer_ai.main`'s uvicorn default. */
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Audio")
    FString BaseUrl = TEXT("http://127.0.0.1:8787");

    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Audio")
    FString SessionId;

    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Audio")
    bool bTtsReady = false;

    /** Explicit per-language voice_id overrides. Empty -> let server decide. */
    TMap<FString, FString> VoiceByLanguage;

    // Internal helpers --------------------------------------------------------
    void DoRequestQuipTts(const FString& Text, const FString& VoiceId);
    void OnTtsResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bSuccess);
    void DoRequestUrl(const FString& Url);
    void OnUrlResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bSuccess);
    void PlayWavBytes(const TArray<uint8>& WavBytes);
    void RefreshReadyFromHealth();
    void OnHealthResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bSuccess);

    /** Escape a string for safe inclusion as a JSON string literal. */
    static FString EscapeJsonString(const FString& In);
};
