#include "BlackjackRules.h"

namespace Blackjack
{
    static FRuleSet MakeVegas()
    {
        FRuleSet R;
        R.Id = ERuleSetId::Vegas;
        R.Name = TEXT("Classic Vegas");
        R.Decks = 6;
        R.bRemoveTens = false;
        R.Penetration = 0.75;
        R.bDealerHitsSoft17 = true;
        R.BlackjackPays = 1.5;
        R.InsurancePays = 2.0;
        R.bAllowSurrender = true;
        R.bAllowDoubleAfterSplit = true;
        R.MaxSplits = 3;
        R.bResplitAces = false;
        R.bSplitAcesOneCardOnly = true;
        R.DoubleAllowed = EDoubleAllowed::AnyTwo;
        R.bDealerPeeksOnTen = true;
        R.bDealerPeeksOnAce = true;
        R.bBonus21s = false;
        R.bPlayerTotalsWinOver17 = false;
        R.MinBet = 5;
        R.MaxBet = 500;
        R.StartingBankroll = 1000;
        return R;
    }

    static FRuleSet MakeSpanish21()
    {
        FRuleSet R = MakeVegas();
        R.Id = ERuleSetId::Spanish21;
        R.Name = TEXT("Spanish 21");
        R.bRemoveTens = true;
        R.bBonus21s = true;
        R.bPlayerTotalsWinOver17 = true;
        return R;
    }

    static FRuleSet MakePontoon()
    {
        FRuleSet R = MakeVegas();
        R.Id = ERuleSetId::Pontoon;
        R.Name = TEXT("Pontoon");
        R.Decks = 8;
        R.BlackjackPays = 2.0;
        R.bAllowSurrender = false;
        R.bBonus21s = true;
        R.bDealerPeeksOnAce = false;
        R.bDealerPeeksOnTen = false;
        R.bPlayerTotalsWinOver17 = true;
        return R;
    }

    static FRuleSet MakeSuperFun21()
    {
        FRuleSet R = MakeVegas();
        R.Id = ERuleSetId::SuperFun21;
        R.Name = TEXT("Super Fun 21");
        R.Decks = 1;
        R.BlackjackPays = 1.0;
        R.bBonus21s = true;
        R.bAllowSurrender = true;
        R.bPlayerTotalsWinOver17 = true;
        return R;
    }

    const FRuleSet& GetPreset(ERuleSetId Id)
    {
        static const FRuleSet Vegas      = MakeVegas();
        static const FRuleSet Spanish21  = MakeSpanish21();
        static const FRuleSet Pontoon    = MakePontoon();
        static const FRuleSet SuperFun21 = MakeSuperFun21();
        switch (Id)
        {
            case ERuleSetId::Spanish21:  return Spanish21;
            case ERuleSetId::Pontoon:    return Pontoon;
            case ERuleSetId::SuperFun21: return SuperFun21;
            case ERuleSetId::Vegas:
            default:                     return Vegas;
        }
    }
}
