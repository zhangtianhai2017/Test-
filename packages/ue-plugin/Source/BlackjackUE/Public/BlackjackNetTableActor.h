// M6 — Net-driven scene glue for the 3D blackjack table.
//
// Drop ABlackjackNetTableActor in the level (or subclass it as a Blueprint).
// In BeginPlay it auto-binds to the UBlackjackNetClient game-instance
// subsystem. Assign: CardActorClass, ChipStackClass, DealerCharacter,
// SeatBankrollStacks (array of 6 chip stacks placed at seat positions),
// SeatBetTransforms (where cards land per seat), DealerBetTransform.
// Call UBlackjackNetClient::Connect(Host, Port, Name) from your menu UI
// to connect; this actor will react to incoming state changes.
//
// Unlike ABlackjackTableActor (which drives a local UBlackjackGameComponent
// built on the frozen C++ rules engine, per D-021), this actor is a pure
// consumer of authoritative server frames surfaced by UBlackjackNetClient
// and never looks at BlackjackCore. Keep them disjoint.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "BlackjackTypes.h"
#include "BlackjackNetClient.h"
#include "BlackjackNetTableActor.generated.h"

class UBlackjackNetClient;
class ABlackjackCardActor;
class ABlackjackChipStackActor;
class ABlackjackDealerCharacter;

// ---------------------------------------------------------------------------
// Forwarding delegates — designers can wire level-blueprint or UMG responses
// here without editing this actor. These mirror the most common net-client
// signals but live on the scene actor so they're easy to assign in-editor.
// ---------------------------------------------------------------------------

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnNetTablePhaseChanged, EBlackjackPhase, NewPhase);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnNetTableBetSettled, int32, SeatIndex, EBlackjackOutcome, Outcome, int32, Payout);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnNetTableRoundOver, const TArray<FBlackjackTableHandResult>&, Results);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnNetTableBankrollChanged, int32, SeatIndex, int32, NewBalance);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnNetTableConnectionState, EBlackjackConnectionState, NewState);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnNetTableSeatAssigned, int32, SeatIndex, const FString&, OwnerClientId);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnNetTableSeatReleased, int32, SeatIndex, bool, bBecameNpc, const FString&, Personality);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnNetTableShoeShuffled);

/** Per-seat card-pointer list. Wrapped in a USTRUCT so we can hold a
 *  TArray of them inside a UPROPERTY (nested TArray<TArray<>> is not
 *  supported by UHT). */
USTRUCT()
struct FBlackjackNetSeatCardList
{
    GENERATED_BODY()

    UPROPERTY() TArray<ABlackjackCardActor*> Cards;
};

/**
 * Scene-facing Actor that subscribes to the UBlackjackNetClient
 * game-instance subsystem and drives the 3D table visuals
 * (dealer character, per-seat chip stacks, card actors).
 *
 * Designers should either place this actor in the level directly or
 * subclass it as a Blueprint and wire the forwarding delegates below.
 */
UCLASS(Blueprintable)
class BLACKJACKUE_API ABlackjackNetTableActor : public AActor
{
    GENERATED_BODY()

public:
    ABlackjackNetTableActor();

    // --- Designer-assignable scene references ------------------------------

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Net")
    TSubclassOf<ABlackjackCardActor> CardActorClass;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Net")
    TSubclassOf<ABlackjackChipStackActor> ChipStackClass;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Net")
    ABlackjackDealerCharacter* DealerCharacter = nullptr;

    /** Bankroll chip stack actors, one per seat (size 6). Placed at each seat's spot by the designer. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Net")
    TArray<ABlackjackChipStackActor*> SeatBankrollStacks;

    /** World-space landing spots for cards dealt to each seat (size 6). */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Net")
    TArray<FTransform> SeatBetTransforms;

    /** World-space landing spot for cards dealt to the dealer. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Net")
    FTransform DealerBetTransform;

    /** Per-card lateral offset applied when stacking multiple cards in one hand. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Net|Layout")
    float CardSpreadX = 8.f;

    /** Bankroll-to-chip-instance divisor (matches ABlackjackTableActor's $25 convention). */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Net|Layout")
    int32 ChipDenomination = 25;

    // --- Forwarding delegates (BlueprintAssignable for designer wiring) ----

    UPROPERTY(BlueprintAssignable, Category = "Blackjack|Net")
    FOnNetTableConnectionState OnConnectionState;

    UPROPERTY(BlueprintAssignable, Category = "Blackjack|Net")
    FOnNetTablePhaseChanged OnPhaseChangedEvent;

    UPROPERTY(BlueprintAssignable, Category = "Blackjack|Net")
    FOnNetTableBetSettled OnBetSettledEvent;

    UPROPERTY(BlueprintAssignable, Category = "Blackjack|Net")
    FOnNetTableRoundOver OnRoundOverEvent;

    UPROPERTY(BlueprintAssignable, Category = "Blackjack|Net")
    FOnNetTableBankrollChanged OnBankrollChangedEvent;

    UPROPERTY(BlueprintAssignable, Category = "Blackjack|Net")
    FOnNetTableSeatAssigned OnSeatAssignedEvent;

    UPROPERTY(BlueprintAssignable, Category = "Blackjack|Net")
    FOnNetTableSeatReleased OnSeatReleasedEvent;

    UPROPERTY(BlueprintAssignable, Category = "Blackjack|Net")
    FOnNetTableShoeShuffled OnShoeShuffledEvent;

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;

    // --- Net-client delegate handlers --------------------------------------

    UFUNCTION() void HandleConnectionStateChanged(EBlackjackConnectionState NewState);
    UFUNCTION() void HandleTableState(const FBlackjackTableStateSnapshot& Snapshot);
    UFUNCTION() void HandlePhaseChanged(EBlackjackPhase NewPhase);
    UFUNCTION() void HandleCardDealt(EBlackjackTarget Target, int32 SeatIndex, int32 HandIndex, FBlackjackCardPayload Card, bool bFaceDown);
    UFUNCTION() void HandleHoleCardRevealed(FBlackjackCardPayload Card);
    UFUNCTION() void HandlePlayerAction(int32 SeatIndex, EBlackjackAction Action, int32 HandIndex);
    UFUNCTION() void HandleHandBust(int32 SeatIndex, int32 HandIndex);
    UFUNCTION() void HandleNaturalBlackjack(int32 SeatIndex, int32 HandIndex);
    UFUNCTION() void HandleBetSettled(int32 SeatIndex, int32 HandIndex, EBlackjackOutcome Outcome, int32 Payout);
    UFUNCTION() void HandleRoundOver(const TArray<FBlackjackTableHandResult>& Results);
    UFUNCTION() void HandleBankrollChanged(int32 SeatIndex, int32 NewBalance, int32 Delta);
    UFUNCTION() void HandleShoeShuffled();
    UFUNCTION() void HandleSeatAssigned(int32 SeatIndex, const FString& OwnerClientId);
    UFUNCTION() void HandleSeatReleased(int32 SeatIndex, bool bBecameNpc, const FString& Personality);

private:
    /** Cached resolved subsystem pointer; null until BeginPlay finds it. */
    UPROPERTY() UBlackjackNetClient* NetClient = nullptr;

    /** Dealer card actors in deal order (index 1 is the hole card). */
    UPROPERTY() TArray<ABlackjackCardActor*> DealerCards;

    /** Per-seat card actor lists. Always size 6 (one bucket per seat). */
    UPROPERTY() TArray<FBlackjackNetSeatCardList> PlayerCardsBySeat;

    /** Owner session id per seat ("" when unoccupied). Always size 6. */
    TArray<FString> SeatOwners;

    /** Resolve the net-client subsystem from the owning GameInstance. */
    UBlackjackNetClient* ResolveNetClient() const;

    /** Bind/unbind helpers keep BeginPlay/EndPlay readable. */
    void BindNetClientDelegates();
    void UnbindNetClientDelegates();

    /** Destroy every spawned card actor and reset bookkeeping. */
    void ClearSpawnedCards();

    /** Convert wire Rank/Suit strings to the engine enum card used by ABlackjackCardActor. */
    static FBlackjackCard PayloadToCard(const FBlackjackCardPayload& Payload);

    /** Initial deck/shoe world location — above the dealer if one is set, else above self. */
    FVector GetDeckSpawnLocation() const;

    /** Compute per-card landing transform for a given seat + card-in-hand index. */
    FTransform GetSeatCardTarget(int32 SeatIndex, int32 CardInHandIndex) const;

    /** Compute per-card landing transform for a dealer card. */
    FTransform GetDealerCardTarget(int32 CardInRowIndex) const;
};
