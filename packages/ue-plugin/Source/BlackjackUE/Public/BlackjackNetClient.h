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

// ---------------------------------------------------------------------------
// Supporting enums / structs for client-originated frames (M5b.1).
// `EBlackjackRuleSet` already lives in BlackjackTypes.h and is reused here.
// ---------------------------------------------------------------------------

UENUM(BlueprintType)
enum class EBlackjackLanguage : uint8
{
    Chinese UMETA(DisplayName = "Chinese (zh)"),
    English UMETA(DisplayName = "English (en)")
};

UENUM(BlueprintType)
enum class EBlackjackGesture : uint8
{
    Confident,
    Nervous,
    PokerFace,
    Taunt,
    Sigh,
    Celebrate
};

UENUM(BlueprintType)
enum class EBlackjackSeatKind : uint8
{
    Empty,
    Human,
    Npc
};

// Dealer-turn hit/stand/bust action reported by the server over the wire
// (distinct from EBlackjackAction, which covers player-driven actions).
UENUM(BlueprintType)
enum class EBlackjackDealerAction : uint8
{
    Hit,
    Stand,
    Bust
};

USTRUCT(BlueprintType)
struct FBlackjackSeatConfig
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Blackjack|Net")
    EBlackjackSeatKind Kind = EBlackjackSeatKind::Empty;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Blackjack|Net")
    FString Name;

    /** One of the NpcPersonality wire values (e.g. "optimal", "chaser"). Only used when Kind == Npc. */
    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Blackjack|Net")
    FString Personality;

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Blackjack|Net")
    int32 Bankroll = 0;
};

// ---------------------------------------------------------------------------
// M5b.2b — server-originated payload structs.
//
// These mirror the shapes produced by packages/game-server/src/protocol/toProtocol.ts
// and are surfaced to Blueprints as BlueprintType USTRUCTs. They intentionally
// use FString Rank/Suit (instead of the richer FBlackjackCard from
// BlackjackTypes.h) because the wire format encodes cards as `{rank,suit}`
// strings with an optional `faceDown` flag for the dealer hole card.
// ---------------------------------------------------------------------------

USTRUCT(BlueprintType)
struct FBlackjackCardPayload
{
    GENERATED_BODY()

    /** "" when bFaceDown == true (e.g. dealer hole card prior to reveal). */
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") FString Rank;

    /** "" when bFaceDown == true (e.g. dealer hole card prior to reveal). */
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") FString Suit;

    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") bool bFaceDown = false;
};

USTRUCT(BlueprintType)
struct FBlackjackHand
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") TArray<FBlackjackCardPayload> Cards;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") int32 Bet = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") bool bDoubled = false;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") bool bStood = false;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") bool bSurrendered = false;
    /** Server-computed total (trust incoming; do not recompute). */
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") int32 Total = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") bool bSoft = false;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") bool bIsBust = false;
};

USTRUCT(BlueprintType)
struct FBlackjackSeatPayload
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") int32 Index = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") EBlackjackSeatKind Kind = EBlackjackSeatKind::Empty;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") FString Name;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") FString Personality;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") int32 Bankroll = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") FString OwnerSessionId;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") int32 PendingBet = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") int32 ActiveHandIndex = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") TArray<FBlackjackHand> Hands;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") float Tilt = 0.f;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") TArray<FString> Gestures;
};

// NOTE: A simpler `FBlackjackHandResult` already exists in BlackjackTypes.h
// (HandIndex + Outcome + Payout + Total + Cards<FBlackjackCard> + Label), used
// by the legacy local-engine components. The net protocol's result adds a
// `SeatIndex` and uses `FBlackjackCardPayload` (strings + faceDown) instead,
// so we expose it as a distinct `FBlackjackTableHandResult` to avoid colliding
// with the existing UHT-registered type.
USTRUCT(BlueprintType)
struct FBlackjackTableHandResult
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") int32 SeatIndex = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") int32 HandIndex = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") EBlackjackOutcome Outcome = EBlackjackOutcome::Loss;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") int32 Payout = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") int32 Total = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") FString Label;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") TArray<FBlackjackCardPayload> Cards;
};

USTRUCT(BlueprintType)
struct FBlackjackTableSummary
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") FString TableId;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") EBlackjackRuleSet RuleSet = EBlackjackRuleSet::Vegas;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") int32 SeatsTaken = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") int32 MaxSeats = 6;
};

USTRUCT(BlueprintType)
struct FBlackjackTableStateSnapshot
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") FString TableId;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") EBlackjackPhase Phase = EBlackjackPhase::Betting;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") EBlackjackRuleSet RuleSet = EBlackjackRuleSet::Vegas;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") int32 MaxSeats = 6;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") int32 ActiveSeatIndex = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") TArray<FBlackjackCardPayload> Dealer;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") TArray<FBlackjackSeatPayload> Seats;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") FString DealerPersona;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") EBlackjackLanguage Language = EBlackjackLanguage::Chinese;
    UPROPERTY(BlueprintReadOnly, Category = "Blackjack|Net") TArray<FBlackjackTableHandResult> RoundResults;
};

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

    // -----------------------------------------------------------------------
    // Client-originated frame senders (M5b.1).
    //
    // Every sender guards on `State == Connected` and silently drops (with a
    // verbose log) if the socket is not ready; callers should consult
    // `GetConnectionState()` before dispatching UI actions.
    // -----------------------------------------------------------------------

    // Lobby ------------------------------------------------------------------
    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void ListTables();

    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void CreateTable(EBlackjackRuleSet RuleSet, int32 MaxSeats, const FString& DealerPersona, EBlackjackLanguage Language);

    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void JoinTable(const FString& TableId, const TArray<int32>& SeatRequest);

    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void LeaveTable();

    // Seat mgmt --------------------------------------------------------------
    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void ConfigureTable(const TArray<FBlackjackSeatConfig>& Seats);

    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void ClaimSeat(int32 SeatIndex, const FString& Name, int32 Bankroll);

    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void ReleaseSeat(int32 SeatIndex, bool bBecomeNpc, const FString& Personality);

    // Gameplay ---------------------------------------------------------------
    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void SendPlaceBet(int32 SeatIndex, int32 Amount, int32 PerfectPairs, int32 TwentyOneP3, int32 LuckyLadies);

    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void SendHit(int32 SeatIndex);

    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void SendStand(int32 SeatIndex);

    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void SendDouble(int32 SeatIndex);

    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void SendSplit(int32 SeatIndex);

    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void SendSurrender(int32 SeatIndex);

    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void SendInsure(int32 SeatIndex, int32 Amount);

    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void SendDeclineInsurance(int32 SeatIndex);

    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void SendNewRound();

    UFUNCTION(BlueprintCallable, Category = "Blackjack|Net")
    void SendGesture(int32 SeatIndex, EBlackjackGesture Gesture);

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

    // Small helper: build a base object with `v` + `type`, ready to have
    // frame-specific fields appended before serialization.
    TSharedRef<FJsonObject> MakeBaseFrame(const TCHAR* Type) const;

    // Serialize + dispatch through SendFrame, with a Connected guard.
    void SerializeAndSend(const TSharedRef<FJsonObject>& Obj, const TCHAR* TypeForLog);

    // Wire-value converters. Must match the Zod enums in
    // packages/game-server/src/protocol/frames.ts exactly.
    static FString RuleSetToWire(EBlackjackRuleSet RuleSet);
    static FString LanguageToWire(EBlackjackLanguage Lang);
    static FString GestureToWire(EBlackjackGesture Gesture);
    static FString SeatKindToWire(EBlackjackSeatKind Kind);

    // Teardown helper: unbind delegates, close socket, release TSharedPtr.
    void ReleaseSocket();

    static constexpr int32 PROTOCOL_VERSION = 1;
};
