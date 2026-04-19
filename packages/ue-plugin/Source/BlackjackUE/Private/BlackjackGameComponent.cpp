#include "BlackjackGameComponent.h"
#include "BlackjackGame.h"

UBlackjackGameComponent::UBlackjackGameComponent()
{
    PrimaryComponentTick.bCanEverTick = false;
}

void UBlackjackGameComponent::BeginPlay()
{
    Super::BeginPlay();
    EnsureGame();
}

void UBlackjackGameComponent::EndPlay(const EEndPlayReason::Type Reason)
{
    if (Game && ListenerHandle != 0) Game->RemoveListener(ListenerHandle);
    Game.Reset();
    Super::EndPlay(Reason);
}

void UBlackjackGameComponent::EnsureGame()
{
    if (Game) return;
    const uint32 Rng = (Seed != 0) ? static_cast<uint32>(Seed) : static_cast<uint32>(FDateTime::UtcNow().GetTicks());
    Game = MakeUnique<Blackjack::FGame>(BlackjackConv::From(RuleSet), Rng);
    PreviousBankroll = Game->GetState().Bankroll;
    ListenerHandle = Game->AddListener([this](const Blackjack::FEngineEvent& E){ HandleEngineEvent(E); });
}

void UBlackjackGameComponent::HandleEngineEvent(const Blackjack::FEngineEvent& E)
{
    using EV = Blackjack::FEngineEvent::EType;
    switch (E.Type)
    {
        case EV::PhaseChanged:
            OnPhaseChanged.Broadcast(BlackjackConv::To(E.Phase));
            break;
        case EV::CardDealt:
            OnCardDealt.Broadcast(
                E.bToDealer ? EBlackjackTarget::Dealer : EBlackjackTarget::Player,
                E.HandIndex,
                BlackjackConv::To(E.Card),
                E.bFaceDown);
            break;
        case EV::HoleCardRevealed:
            OnHoleCardRevealed.Broadcast(BlackjackConv::To(E.Card));
            break;
        case EV::PlayerAction:
            if (E.ActionName == TEXT("HIT"))       OnPlayerAction.Broadcast(EBlackjackAction::Hit, E.HandIndex);
            else if (E.ActionName == TEXT("STAND")) OnPlayerAction.Broadcast(EBlackjackAction::Stand, E.HandIndex);
            else if (E.ActionName == TEXT("DOUBLE")) OnPlayerAction.Broadcast(EBlackjackAction::Double, E.HandIndex);
            else if (E.ActionName == TEXT("SPLIT")) OnPlayerAction.Broadcast(EBlackjackAction::Split, E.HandIndex);
            else if (E.ActionName == TEXT("SURRENDER")) OnPlayerAction.Broadcast(EBlackjackAction::Surrender, E.HandIndex);
            break;
        case EV::HandBust:
            OnHandBust.Broadcast(E.HandIndex);
            break;
        case EV::NaturalBlackjack:
            OnNaturalBlackjack.Broadcast(E.HandIndex);
            break;
        case EV::BetSettled:
            OnBetSettled.Broadcast(E.HandIndex, BlackjackConv::To(E.Outcome), E.Payout);
            break;
        case EV::RoundOver:
        {
            TArray<FBlackjackHandResult> Results;
            for (const Blackjack::FHandResult& R : E.RoundResults) Results.Add(BlackjackConv::To(R));
            OnRoundOver.Broadcast(Results);
            break;
        }
        case EV::BankrollChanged:
            OnBankrollChanged.Broadcast(E.Bankroll, E.Delta);
            if (E.Delta >= BigWinThreshold) OnBigWin.Broadcast(E.Delta);
            if (E.Bankroll <= 0) OnBankrupt.Broadcast();
            PreviousBankroll = E.Bankroll;
            break;
        case EV::SideBetWin:
        {
            EBlackjackSideBet Kind = EBlackjackSideBet::PerfectPairs;
            if (E.SideBetKind == TEXT("21+3")) Kind = EBlackjackSideBet::TwentyOneP3;
            else if (E.SideBetKind == TEXT("luckyLadies")) Kind = EBlackjackSideBet::LuckyLadies;
            OnSideBetWin.Broadcast(Kind, E.Payout, E.Label);
            break;
        }
        default:
            break;
    }
}

void UBlackjackGameComponent::PlaceBet(int32 Amount, FBlackjackSideBets SideBets)
{
    EnsureGame();
    Blackjack::FAction A;
    A.Type = Blackjack::EActionType::PlaceBet;
    A.Amount = Amount;
    A.SideBets = { SideBets.PerfectPairs, SideBets.TwentyOneP3, SideBets.LuckyLadies };
    Game->Dispatch(A);
}

#define SIMPLE_ACTION(Name, T) \
void UBlackjackGameComponent::Name() { EnsureGame(); Blackjack::FAction A; A.Type = T; Game->Dispatch(A); }

SIMPLE_ACTION(Hit,      Blackjack::EActionType::Hit)
SIMPLE_ACTION(Stand,    Blackjack::EActionType::Stand)
SIMPLE_ACTION(Double,   Blackjack::EActionType::Double)
SIMPLE_ACTION(Split,    Blackjack::EActionType::Split)
SIMPLE_ACTION(Surrender,Blackjack::EActionType::Surrender)
SIMPLE_ACTION(DeclineInsurance, Blackjack::EActionType::DeclineInsurance)
SIMPLE_ACTION(NewRound, Blackjack::EActionType::NewRound)

#undef SIMPLE_ACTION

void UBlackjackGameComponent::Insure(int32 Amount)
{
    EnsureGame();
    Blackjack::FAction A;
    A.Type = Blackjack::EActionType::Insure;
    A.Amount = Amount;
    Game->Dispatch(A);
}

void UBlackjackGameComponent::SetRuleSetAsset(EBlackjackRuleSet NewRuleSet)
{
    EnsureGame();
    Blackjack::FAction A;
    A.Type = Blackjack::EActionType::SetRuleSet;
    A.Preset = BlackjackConv::From(NewRuleSet);
    Game->Dispatch(A);
    RuleSet = NewRuleSet;
}

FBlackjackStateSnapshot UBlackjackGameComponent::GetSnapshot() const
{
    FBlackjackStateSnapshot Out;
    if (!Game) return Out;
    const Blackjack::FSnapshot S = Game->GetState();
    Out.Phase = BlackjackConv::To(S.Phase);
    Out.RuleSet = BlackjackConv::To(S.Rules.Id);
    Out.Bankroll = S.Bankroll;
    for (const Blackjack::FCard& C : S.Dealer) Out.Dealer.Add(BlackjackConv::To(C));
    Out.bDealerHoleHidden = S.bDealerHoleHidden;
    Out.ActiveHandIndex = S.ActiveHandIndex;
    for (const Blackjack::FHandResult& R : S.RoundResults) Out.RoundResults.Add(BlackjackConv::To(R));
    return Out;
}

TArray<EBlackjackAction> UBlackjackGameComponent::GetLegalActions() const
{
    TArray<EBlackjackAction> Out;
    if (!Game) return Out;
    for (Blackjack::EActionType A : Game->GetLegalActions()) Out.Add(BlackjackConv::To(A));
    return Out;
}

int32 UBlackjackGameComponent::GetBankroll() const
{
    return Game ? Game->GetState().Bankroll : 0;
}
