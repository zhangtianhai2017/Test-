#include "BlackjackDealer.h"
#include "BlackjackHand.h"

namespace Blackjack
{
    bool DealerShouldHit(const TArray<FCard>& Cards, const FRuleSet& Rules)
    {
        const FHandValue V = Evaluate(Cards);
        if (V.bBust) return false;
        if (V.Total < 17) return true;
        if (V.Total == 17 && V.bSoft && Rules.bDealerHitsSoft17) return true;
        return false;
    }
}
