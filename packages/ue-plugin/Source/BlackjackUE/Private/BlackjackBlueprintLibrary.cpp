#include "BlackjackBlueprintLibrary.h"
#include "BlackjackHand.h"

FString UBlackjackBlueprintLibrary::CardToString(const FBlackjackCard& Card)
{
    const Blackjack::FCard C = BlackjackConv::From(Card);
    return FString::Printf(TEXT("%s%s"), Blackjack::RankToChar(C.Rank), Blackjack::SuitToChar(C.Suit));
}

static TArray<Blackjack::FCard> ToNative(const TArray<FBlackjackCard>& Cards)
{
    TArray<Blackjack::FCard> Out;
    Out.Reserve(Cards.Num());
    for (const FBlackjackCard& C : Cards) Out.Add(BlackjackConv::From(C));
    return Out;
}

int32 UBlackjackBlueprintLibrary::HandTotal(const TArray<FBlackjackCard>& Cards)
{
    return Blackjack::Evaluate(ToNative(Cards)).Total;
}

bool UBlackjackBlueprintLibrary::IsBlackjack(const TArray<FBlackjackCard>& Cards)
{
    return Blackjack::IsBlackjack(ToNative(Cards));
}

bool UBlackjackBlueprintLibrary::IsBust(const TArray<FBlackjackCard>& Cards)
{
    return Blackjack::Evaluate(ToNative(Cards)).bBust;
}

FString UBlackjackBlueprintLibrary::OutcomeToString(EBlackjackOutcome Outcome)
{
    switch (Outcome)
    {
        case EBlackjackOutcome::Win: return TEXT("win");
        case EBlackjackOutcome::Loss: return TEXT("loss");
        case EBlackjackOutcome::Push: return TEXT("push");
        case EBlackjackOutcome::Blackjack: return TEXT("blackjack");
        case EBlackjackOutcome::Surrender: return TEXT("surrender");
        case EBlackjackOutcome::Bust: return TEXT("bust");
    }
    return TEXT("");
}

FString UBlackjackBlueprintLibrary::PhaseToString(EBlackjackPhase Phase)
{
    static const TCHAR* Names[] = { TEXT("betting"), TEXT("dealing"), TEXT("insurance"), TEXT("playerTurn"), TEXT("dealerTurn"), TEXT("settlement"), TEXT("roundOver") };
    const uint8 Idx = static_cast<uint8>(Phase);
    return Idx < UE_ARRAY_COUNT(Names) ? Names[Idx] : TEXT("");
}
