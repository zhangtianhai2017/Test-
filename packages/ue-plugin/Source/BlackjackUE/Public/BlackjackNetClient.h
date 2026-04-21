#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "BlackjackTypes.h"
#include "BlackjackNetClient.generated.h"

class IWebSocket;
class FJsonObject;

UENUM(BlueprintType)
enum class EBlackjackConnectionState : uint8
{
    Disconnected,
    Connecting,
    Awaiting_Hello,
    Connected,
    Reconnecting,
    Closed
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnBlackjackConnectionStateChanged, EBlackjackConnectionState, NewState);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnBlackjackWelcome, const FString&, SessionId, int32, ReconnectGraceSeconds);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnBlackjackServerError, const FString&, Code, const FString&, Message);

/**
 * Authoritative game-server client. Always connects (single-player mode
 * connects to a locally-spawned server subprocess on 127.0.0.1). Handles
 * HELLO/WELCOME, PING/PONG keepalive, disconnect + resume.
 *
 * Full frame routing (CARD_DEALT, TABLE_STATE, etc.) lands in M5b.
 */
UCLASS()
class BLACKJACKUE_API UBlackjackNetClient : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

    /** Connect to game-server. Call with the local or LAN host + port + the player's nickname. */
    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void Connect(const FString& Host, int32 Port, const FString& InDisplayName);

    /** Gracefully close the connection. */
    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void Disconnect();

    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "Blackjack|Net")
    EBlackjackConnectionState GetConnectionState() const { return State; }

    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "Blackjack|Net")
    FString GetSessionId() const { return SessionId; }

    /** Fired on every state transition clients typically hook this for UI spinners. */
    UPROPERTY(BlueprintAssignable, Category = "Blackjack|Net")
    FOnBlackjackConnectionStateChanged OnConnectionStateChanged;

    /** Fired once after the server responds with WELCOME. */
    UPROPERTY(BlueprintAssignable, Category = "Blackjack|Net")
    FOnBlackjackWelcome OnWelcome;

    /** Fired for any server-side ERROR frame (before M5b wires specialized error routing). */
    UPROPERTY(BlueprintAssignable, Category = "Blackjack|Net")
    FOnBlackjackServerError OnServerError;

    /** Reconnect grace window advertised by the server. Populated on WELCOME. */
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net")
    int32 ReconnectGraceSeconds = 0;

    /** Seconds between PINGs. Default 10. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Net")
    float PingIntervalSeconds = 10.f;

protected:
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net")
    EBlackjackConnectionState State = EBlackjackConnectionState::Disconnected;

    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net")
    FString SessionId;

    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net")
    FString DisplayName;

    // The underlying socket (held as a TSharedPtr -- not a UPROPERTY).
    TSharedPtr<IWebSocket> Socket;
    FTimerHandle PingTimerHandle;
    FString PendingResumeSessionId;  // set if Connect-after-disconnect tries to resume

    void SetState(EBlackjackConnectionState NewState);
    void SendHello();
    void SendPing();
    void StartPingTimer();
    void StopPingTimer();

    // WebSocket callbacks:
    void HandleConnected();
    void HandleConnectionError(const FString& Error);
    void HandleClosed(int32 StatusCode, const FString& Reason, bool bWasClean);
    void HandleMessage(const FString& Message);

    // Frame helpers:
    void SendFrame(const FString& JsonStr);
    void DispatchFrame(const TSharedPtr<FJsonObject>& Frame);

    // Teardown helper: unbind delegates, close socket, release TSharedPtr.
    void ReleaseSocket();

    static constexpr int32 PROTOCOL_VERSION = 1;
};
