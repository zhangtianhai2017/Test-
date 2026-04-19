#pragma once

#include "CoreMinimal.h"
#include "BlackjackCards.h"

namespace Blackjack
{
    struct FSideBetResult
    {
        int32 Payout;
        FString Label;
    };

    BLACKJACKCORE_API FSideBetResult EvalPerfectPairs(const TArray<FCard>& PlayerTwo);
    BLACKJACKCORE_API FSideBetResult EvalTwentyOnePlusThree(const TArray<FCard>& PlayerTwo, const FCard& DealerUp, bool bHaveDealer);
    BLACKJACKCORE_API FSideBetResult EvalLuckyLadies(const TArray<FCard>& PlayerTwo, const TArray<FCard>& DealerFull);
}
