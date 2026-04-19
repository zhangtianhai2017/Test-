#pragma once

#include "CoreMinimal.h"
#include "BlackjackCards.h"
#include "BlackjackRules.h"

namespace Blackjack
{
    BLACKJACKCORE_API bool DealerShouldHit(const TArray<FCard>& Cards, const FRuleSet& Rules);
}
