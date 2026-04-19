#include "BlackjackHand.h"

namespace Blackjack
{
    FHandValue Evaluate(const TArray<FCard>& Cards)
    {
        int32 Total = 0;
        int32 Aces = 0;
        for (const FCard& C : Cards)
        {
            Total += RankValue(C.Rank);
            if (C.Rank == ERank::Ace) ++Aces;
        }
        bool bSoft = false;
        if (Aces > 0 && Total + 10 <= 21)
        {
            Total += 10;
            bSoft = true;
        }
        return { Total, bSoft, Total > 21, Total == 21 };
    }

    bool IsBlackjack(const TArray<FCard>& Cards)
    {
        if (Cards.Num() != 2) return false;
        return Evaluate(Cards).Total == 21;
    }

    bool IsPair(const TArray<FCard>& Cards)
    {
        if (Cards.Num() != 2) return false;
        return RankValue(Cards[0].Rank) == RankValue(Cards[1].Rank);
    }
}
