#pragma once

#include "CoreMinimal.h"

namespace Blackjack
{
    enum class ERuleSetId : uint8 { Vegas, Spanish21, Pontoon, SuperFun21 };

    enum class EDoubleAllowed : uint8 { AnyTwo, NineTenEleven, TenEleven };

    struct FRuleSet
    {
        ERuleSetId Id;
        FString Name;
        int32 Decks;
        bool bRemoveTens;
        double Penetration;
        bool bDealerHitsSoft17;
        double BlackjackPays;
        double InsurancePays;
        bool bAllowSurrender;
        bool bAllowDoubleAfterSplit;
        int32 MaxSplits;
        bool bResplitAces;
        bool bSplitAcesOneCardOnly;
        EDoubleAllowed DoubleAllowed;
        bool bDealerPeeksOnTen;
        bool bDealerPeeksOnAce;
        bool bBonus21s;
        bool bPlayerTotalsWinOver17;
        int32 MinBet;
        int32 MaxBet;
        int32 StartingBankroll;
    };

    BLACKJACKCORE_API const FRuleSet& GetPreset(ERuleSetId Id);
}
