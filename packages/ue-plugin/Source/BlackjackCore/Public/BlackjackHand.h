#pragma once

#include "CoreMinimal.h"
#include "BlackjackCards.h"

namespace Blackjack
{
    struct FHandValue
    {
        int32 Total;
        bool bSoft;
        bool bBust;
        bool bIs21;
    };

    BLACKJACKCORE_API FHandValue Evaluate(const TArray<FCard>& Cards);
    BLACKJACKCORE_API bool IsBlackjack(const TArray<FCard>& Cards);
    BLACKJACKCORE_API bool IsPair(const TArray<FCard>& Cards);
}
