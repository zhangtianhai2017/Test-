// M6 — implementation of ABlackjackNetTableActor.

#include "BlackjackNetTableActor.h"

#include "BlackjackCardActor.h"
#include "BlackjackChipStackActor.h"
#include "BlackjackDealerCharacter.h"
#include "BlackjackNetClient.h"

#include "Engine/GameInstance.h"
#include "Engine/World.h"

DEFINE_LOG_CATEGORY_STATIC(LogBlackjackNetTable, Log, All);

static constexpr int32 kSeatCount = 6;

ABlackjackNetTableActor::ABlackjackNetTableActor()
{
    PrimaryActorTick.bCanEverTick = false;

    CardActorClass = ABlackjackCardActor::StaticClass();
    ChipStackClass = ABlackjackChipStackActor::StaticClass();

    SeatBankrollStacks.SetNum(kSeatCount);
    SeatBetTransforms.SetNum(kSeatCount);
    PlayerCardsBySeat.SetNum(kSeatCount);
    SeatOwners.SetNum(kSeatCount);
}

void ABlackjackNetTableActor::BeginPlay()
{
    Super::BeginPlay();

    NetClient = ResolveNetClient();
    if (!NetClient)
    {
        UE_LOG(LogBlackjackNetTable, Warning,
            TEXT("ABlackjackNetTableActor: no UBlackjackNetClient subsystem available; scene will not react to server frames."));
        return;
    }

    BindNetClientDelegates();
}

void ABlackjackNetTableActor::EndPlay(const EEndPlayReason::Type Reason)
{
    UnbindNetClientDelegates();
    // Don't destroy card actors here: the world is already tearing down, and
    // doing so from a delegate callstack is unsafe. Leave cleanup to GC/world
    // teardown. The in-round ClearSpawnedCards path is safe because it runs
    // from OnPhaseChanged(Betting), which does not re-enter this actor.
    NetClient = nullptr;
    Super::EndPlay(Reason);
}

UBlackjackNetClient* ABlackjackNetTableActor::ResolveNetClient() const
{
    if (const UWorld* World = GetWorld())
    {
        if (UGameInstance* GI = World->GetGameInstance())
        {
            return GI->GetSubsystem<UBlackjackNetClient>();
        }
    }
    return nullptr;
}

void ABlackjackNetTableActor::BindNetClientDelegates()
{
    if (!NetClient) return;

    NetClient->OnConnectionStateChanged.AddDynamic(this, &ABlackjackNetTableActor::HandleConnectionStateChanged);
    NetClient->OnTableState.AddDynamic(this, &ABlackjackNetTableActor::HandleTableState);
    NetClient->OnPhaseChanged.AddDynamic(this, &ABlackjackNetTableActor::HandlePhaseChanged);
    NetClient->OnCardDealt.AddDynamic(this, &ABlackjackNetTableActor::HandleCardDealt);
    NetClient->OnHoleCardRevealed.AddDynamic(this, &ABlackjackNetTableActor::HandleHoleCardRevealed);
    NetClient->OnPlayerAction.AddDynamic(this, &ABlackjackNetTableActor::HandlePlayerAction);
    NetClient->OnHandBust.AddDynamic(this, &ABlackjackNetTableActor::HandleHandBust);
    NetClient->OnNaturalBlackjack.AddDynamic(this, &ABlackjackNetTableActor::HandleNaturalBlackjack);
    NetClient->OnBetSettled.AddDynamic(this, &ABlackjackNetTableActor::HandleBetSettled);
    NetClient->OnRoundOver.AddDynamic(this, &ABlackjackNetTableActor::HandleRoundOver);
    NetClient->OnBankrollChanged.AddDynamic(this, &ABlackjackNetTableActor::HandleBankrollChanged);
    NetClient->OnShoeShuffled.AddDynamic(this, &ABlackjackNetTableActor::HandleShoeShuffled);
    NetClient->OnSeatAssigned.AddDynamic(this, &ABlackjackNetTableActor::HandleSeatAssigned);
    NetClient->OnSeatReleased.AddDynamic(this, &ABlackjackNetTableActor::HandleSeatReleased);
}

void ABlackjackNetTableActor::UnbindNetClientDelegates()
{
    if (!NetClient) return;

    NetClient->OnConnectionStateChanged.RemoveDynamic(this, &ABlackjackNetTableActor::HandleConnectionStateChanged);
    NetClient->OnTableState.RemoveDynamic(this, &ABlackjackNetTableActor::HandleTableState);
    NetClient->OnPhaseChanged.RemoveDynamic(this, &ABlackjackNetTableActor::HandlePhaseChanged);
    NetClient->OnCardDealt.RemoveDynamic(this, &ABlackjackNetTableActor::HandleCardDealt);
    NetClient->OnHoleCardRevealed.RemoveDynamic(this, &ABlackjackNetTableActor::HandleHoleCardRevealed);
    NetClient->OnPlayerAction.RemoveDynamic(this, &ABlackjackNetTableActor::HandlePlayerAction);
    NetClient->OnHandBust.RemoveDynamic(this, &ABlackjackNetTableActor::HandleHandBust);
    NetClient->OnNaturalBlackjack.RemoveDynamic(this, &ABlackjackNetTableActor::HandleNaturalBlackjack);
    NetClient->OnBetSettled.RemoveDynamic(this, &ABlackjackNetTableActor::HandleBetSettled);
    NetClient->OnRoundOver.RemoveDynamic(this, &ABlackjackNetTableActor::HandleRoundOver);
    NetClient->OnBankrollChanged.RemoveDynamic(this, &ABlackjackNetTableActor::HandleBankrollChanged);
    NetClient->OnShoeShuffled.RemoveDynamic(this, &ABlackjackNetTableActor::HandleShoeShuffled);
    NetClient->OnSeatAssigned.RemoveDynamic(this, &ABlackjackNetTableActor::HandleSeatAssigned);
    NetClient->OnSeatReleased.RemoveDynamic(this, &ABlackjackNetTableActor::HandleSeatReleased);
}

// ---------------------------------------------------------------------------
// Wire payload -> engine card conversion.
//
// FBlackjackCardPayload uses string ("A", "10", "K", "S"/"H"/"D"/"C") fields
// while ABlackjackCardActor::InitializeCard takes an FBlackjackCard (enum
// rank/suit). Face-down dealer hole cards come in with empty Rank/Suit; we
// fall back to an Ace of Spades placeholder for those because the visual is
// face-down anyway (the real rank arrives later in OnHoleCardRevealed).
// ---------------------------------------------------------------------------
FBlackjackCard ABlackjackNetTableActor::PayloadToCard(const FBlackjackCardPayload& Payload)
{
    FBlackjackCard Out;
    Out.Rank = EBlackjackRank::Ace;
    Out.Suit = EBlackjackSuit::Spades;

    const FString& R = Payload.Rank;
    if      (R == TEXT("A"))  Out.Rank = EBlackjackRank::Ace;
    else if (R == TEXT("2"))  Out.Rank = EBlackjackRank::Two;
    else if (R == TEXT("3"))  Out.Rank = EBlackjackRank::Three;
    else if (R == TEXT("4"))  Out.Rank = EBlackjackRank::Four;
    else if (R == TEXT("5"))  Out.Rank = EBlackjackRank::Five;
    else if (R == TEXT("6"))  Out.Rank = EBlackjackRank::Six;
    else if (R == TEXT("7"))  Out.Rank = EBlackjackRank::Seven;
    else if (R == TEXT("8"))  Out.Rank = EBlackjackRank::Eight;
    else if (R == TEXT("9"))  Out.Rank = EBlackjackRank::Nine;
    else if (R == TEXT("10")) Out.Rank = EBlackjackRank::Ten;
    else if (R == TEXT("J"))  Out.Rank = EBlackjackRank::Jack;
    else if (R == TEXT("Q"))  Out.Rank = EBlackjackRank::Queen;
    else if (R == TEXT("K"))  Out.Rank = EBlackjackRank::King;

    const FString& S = Payload.Suit;
    if      (S == TEXT("S")) Out.Suit = EBlackjackSuit::Spades;
    else if (S == TEXT("H")) Out.Suit = EBlackjackSuit::Hearts;
    else if (S == TEXT("D")) Out.Suit = EBlackjackSuit::Diamonds;
    else if (S == TEXT("C")) Out.Suit = EBlackjackSuit::Clubs;

    return Out;
}

FVector ABlackjackNetTableActor::GetDeckSpawnLocation() const
{
    if (DealerCharacter)
    {
        return DealerCharacter->GetActorLocation() + FVector(0.f, 0.f, 100.f);
    }
    return GetActorLocation() + FVector(0.f, 0.f, 100.f);
}

FTransform ABlackjackNetTableActor::GetSeatCardTarget(int32 SeatIndex, int32 CardInHandIndex) const
{
    FTransform Base;
    if (SeatBetTransforms.IsValidIndex(SeatIndex))
    {
        Base = SeatBetTransforms[SeatIndex];
    }
    else
    {
        Base = GetActorTransform();
    }
    FVector Loc = Base.GetLocation() + FVector(CardInHandIndex * CardSpreadX, 0.f, 0.f);
    return FTransform(Base.GetRotation(), Loc, Base.GetScale3D());
}

FTransform ABlackjackNetTableActor::GetDealerCardTarget(int32 CardInRowIndex) const
{
    const FTransform& Base = DealerBetTransform;
    FVector Loc = Base.GetLocation() + FVector(CardInRowIndex * CardSpreadX, 0.f, 0.f);
    return FTransform(Base.GetRotation(), Loc, Base.GetScale3D());
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

void ABlackjackNetTableActor::HandleConnectionStateChanged(EBlackjackConnectionState NewState)
{
    OnConnectionState.Broadcast(NewState);
}

void ABlackjackNetTableActor::HandleTableState(const FBlackjackTableStateSnapshot& Snapshot)
{
    // A full snapshot is the server telling us to re-establish ground truth:
    // clear any spawned card actors and replay ownership from the snapshot.
    // (Replaying every card as a visual is left as a TODO — initial visuals
    // should ideally just reflect the final dealt state, not re-animate.)
    ClearSpawnedCards();

    for (int32 i = 0; i < kSeatCount; ++i)
    {
        SeatOwners[i].Reset();
    }
    for (const FBlackjackSeatPayload& Seat : Snapshot.Seats)
    {
        if (Seat.Index >= 0 && Seat.Index < kSeatCount)
        {
            SeatOwners[Seat.Index] = Seat.OwnerSessionId;
            if (SeatBankrollStacks.IsValidIndex(Seat.Index) && SeatBankrollStacks[Seat.Index] && ChipDenomination > 0)
            {
                SeatBankrollStacks[Seat.Index]->SetChipCount(Seat.Bankroll / ChipDenomination);
            }
        }
    }

    UE_LOG(LogBlackjackNetTable, Log, TEXT("TABLE_STATE: table=%s phase=%d seats=%d"),
        *Snapshot.TableId, (int32)Snapshot.Phase, Snapshot.Seats.Num());
}

void ABlackjackNetTableActor::HandlePhaseChanged(EBlackjackPhase NewPhase)
{
    UE_LOG(LogBlackjackNetTable, Log, TEXT("PHASE_CHANGED: %d"), (int32)NewPhase);

    if (NewPhase == EBlackjackPhase::Betting)
    {
        // New round starting — tear down the previous round's cards.
        // Safe because OnPhaseChanged is a straight broadcast from the net
        // client and doesn't re-enter this actor via a card actor's dtor.
        ClearSpawnedCards();
    }
    else if (NewPhase == EBlackjackPhase::Dealing)
    {
        if (DealerCharacter) DealerCharacter->PlayDeal();
    }

    OnPhaseChangedEvent.Broadcast(NewPhase);
}

void ABlackjackNetTableActor::HandleCardDealt(EBlackjackTarget Target, int32 SeatIndex, int32 HandIndex, FBlackjackCardPayload Card, bool bFaceDown)
{
    if (!CardActorClass || !GetWorld())
    {
        return;
    }

    const FVector FromLoc = GetDeckSpawnLocation();
    FTransform TargetXform;
    int32 CardInHandIndex = 0;

    if (Target == EBlackjackTarget::Dealer)
    {
        CardInHandIndex = DealerCards.Num();
        TargetXform = GetDealerCardTarget(CardInHandIndex);
    }
    else
    {
        if (!PlayerCardsBySeat.IsValidIndex(SeatIndex))
        {
            UE_LOG(LogBlackjackNetTable, Warning,
                TEXT("CARD_DEALT for out-of-range seat %d — dropping"), SeatIndex);
            return;
        }
        CardInHandIndex = PlayerCardsBySeat[SeatIndex].Cards.Num();
        TargetXform = GetSeatCardTarget(SeatIndex, CardInHandIndex);
    }

    FActorSpawnParameters Sp;
    Sp.Owner = this;
    ABlackjackCardActor* CardActor = GetWorld()->SpawnActor<ABlackjackCardActor>(
        CardActorClass, FromLoc, FRotator::ZeroRotator, Sp);
    if (!CardActor) return;

    const FBlackjackCard EngineCard = PayloadToCard(Card);
    CardActor->InitializeCard(EngineCard, bFaceDown);
    CardActor->PlayDealAnimation(FromLoc, TargetXform.GetLocation(), TargetXform.GetRotation().Rotator());

    if (Target == EBlackjackTarget::Dealer)
    {
        DealerCards.Add(CardActor);
    }
    else
    {
        PlayerCardsBySeat[SeatIndex].Cards.Add(CardActor);
        // Dealer character flourish when dealing to a player seat.
        if (DealerCharacter) DealerCharacter->PlayDeal();
    }
}

void ABlackjackNetTableActor::HandleHoleCardRevealed(FBlackjackCardPayload Card)
{
    // Dealer's second dealt card is the hole card.
    if (DealerCards.IsValidIndex(1) && DealerCards[1])
    {
        // Re-initialize so the face texture reflects the now-revealed card
        // (the initial deal passed a blank payload because the server masked
        // the rank/suit while face-down).
        const FBlackjackCard EngineCard = PayloadToCard(Card);
        DealerCards[1]->InitializeCard(EngineCard, /*bInFaceDown=*/false);
        DealerCards[1]->FlipFaceUp();
    }
    if (DealerCharacter) DealerCharacter->PlayFlipHole();
}

void ABlackjackNetTableActor::HandlePlayerAction(int32 SeatIndex, EBlackjackAction Action, int32 HandIndex)
{
    // v1: log only. Per-seat avatar animations land in M7 Emote System.
    UE_LOG(LogBlackjackNetTable, Log, TEXT("PLAYER_ACTION: seat=%d action=%d hand=%d"),
        SeatIndex, (int32)Action, HandIndex);
}

void ABlackjackNetTableActor::HandleHandBust(int32 SeatIndex, int32 HandIndex)
{
    // TODO(M7): trigger a "bust" chair emote on the affected seat.
    UE_LOG(LogBlackjackNetTable, Log, TEXT("HAND_BUST: seat=%d hand=%d"), SeatIndex, HandIndex);
}

void ABlackjackNetTableActor::HandleNaturalBlackjack(int32 SeatIndex, int32 HandIndex)
{
    // TODO(M7): trigger a "natural BJ" chair emote on the affected seat.
    UE_LOG(LogBlackjackNetTable, Log, TEXT("NATURAL_BJ: seat=%d hand=%d"), SeatIndex, HandIndex);
}

void ABlackjackNetTableActor::HandleBetSettled(int32 SeatIndex, int32 HandIndex, EBlackjackOutcome Outcome, int32 Payout)
{
    UE_LOG(LogBlackjackNetTable, Log, TEXT("BET_SETTLED: seat=%d hand=%d outcome=%d payout=%d"),
        SeatIndex, HandIndex, (int32)Outcome, Payout);
    OnBetSettledEvent.Broadcast(SeatIndex, Outcome, Payout);
}

void ABlackjackNetTableActor::HandleRoundOver(const TArray<FBlackjackTableHandResult>& Results)
{
    // Dealer emote choice: pay vs. collect based on whether any seat won.
    if (DealerCharacter)
    {
        bool bAnyWin = false;
        for (const FBlackjackTableHandResult& R : Results)
        {
            if (R.Outcome == EBlackjackOutcome::Win || R.Outcome == EBlackjackOutcome::Blackjack)
            {
                bAnyWin = true;
                break;
            }
        }
        if (bAnyWin) DealerCharacter->PlayPay();
        else         DealerCharacter->PlayCollect();
    }
    OnRoundOverEvent.Broadcast(Results);
}

void ABlackjackNetTableActor::HandleBankrollChanged(int32 SeatIndex, int32 NewBalance, int32 /*Delta*/)
{
    if (SeatBankrollStacks.IsValidIndex(SeatIndex) && SeatBankrollStacks[SeatIndex] && ChipDenomination > 0)
    {
        SeatBankrollStacks[SeatIndex]->SetChipCount(NewBalance / ChipDenomination);
    }
    OnBankrollChangedEvent.Broadcast(SeatIndex, NewBalance);
}

void ABlackjackNetTableActor::HandleShoeShuffled()
{
    // Optional visual; real montage wiring happens in BP or M7.
    UE_LOG(LogBlackjackNetTable, Log, TEXT("SHOE_SHUFFLED"));
    OnShoeShuffledEvent.Broadcast();
}

void ABlackjackNetTableActor::HandleSeatAssigned(int32 SeatIndex, const FString& OwnerClientId)
{
    if (SeatOwners.IsValidIndex(SeatIndex))
    {
        SeatOwners[SeatIndex] = OwnerClientId;
    }
    OnSeatAssignedEvent.Broadcast(SeatIndex, OwnerClientId);
}

void ABlackjackNetTableActor::HandleSeatReleased(int32 SeatIndex, bool bBecameNpc, const FString& Personality)
{
    if (SeatOwners.IsValidIndex(SeatIndex))
    {
        SeatOwners[SeatIndex].Reset();
    }
    OnSeatReleasedEvent.Broadcast(SeatIndex, bBecameNpc, Personality);
}

void ABlackjackNetTableActor::ClearSpawnedCards()
{
    for (ABlackjackCardActor* C : DealerCards)
    {
        if (C) C->Destroy();
    }
    DealerCards.Reset();

    for (FBlackjackNetSeatCardList& Bucket : PlayerCardsBySeat)
    {
        for (ABlackjackCardActor* C : Bucket.Cards)
        {
            if (C) C->Destroy();
        }
        Bucket.Cards.Reset();
    }
}
