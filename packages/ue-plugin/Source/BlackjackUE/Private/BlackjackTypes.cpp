#include "BlackjackTypes.h"

namespace BlackjackConv
{
    FBlackjackCard To(const Blackjack::FCard& C)
    {
        FBlackjackCard Out;
        Out.Rank = static_cast<EBlackjackRank>(C.Rank);
        Out.Suit = static_cast<EBlackjackSuit>(C.Suit);
        return Out;
    }
    Blackjack::FCard From(const FBlackjackCard& C)
    {
        return { static_cast<Blackjack::ERank>(C.Rank), static_cast<Blackjack::ESuit>(C.Suit) };
    }
    EBlackjackRuleSet To(Blackjack::ERuleSetId R) { return static_cast<EBlackjackRuleSet>(R); }
    Blackjack::ERuleSetId From(EBlackjackRuleSet R) { return static_cast<Blackjack::ERuleSetId>(R); }
    EBlackjackPhase To(Blackjack::EPhase P) { return static_cast<EBlackjackPhase>(P); }
    EBlackjackOutcome To(Blackjack::EOutcome O) { return static_cast<EBlackjackOutcome>(O); }
    EBlackjackAction To(Blackjack::EActionType A)
    {
        switch (A)
        {
            case Blackjack::EActionType::PlaceBet: return EBlackjackAction::PlaceBet;
            case Blackjack::EActionType::Hit:      return EBlackjackAction::Hit;
            case Blackjack::EActionType::Stand:    return EBlackjackAction::Stand;
            case Blackjack::EActionType::Double:   return EBlackjackAction::Double;
            case Blackjack::EActionType::Split:    return EBlackjackAction::Split;
            case Blackjack::EActionType::Surrender:return EBlackjackAction::Surrender;
            case Blackjack::EActionType::Insure:   return EBlackjackAction::Insure;
            case Blackjack::EActionType::DeclineInsurance: return EBlackjackAction::DeclineInsurance;
            case Blackjack::EActionType::NewRound: return EBlackjackAction::NewRound;
            case Blackjack::EActionType::SetRuleSet: return EBlackjackAction::SetRuleSet;
            case Blackjack::EActionType::Deal:     return EBlackjackAction::PlaceBet;
        }
        return EBlackjackAction::Stand;
    }
    Blackjack::EActionType From(EBlackjackAction A)
    {
        switch (A)
        {
            case EBlackjackAction::PlaceBet: return Blackjack::EActionType::PlaceBet;
            case EBlackjackAction::Hit:      return Blackjack::EActionType::Hit;
            case EBlackjackAction::Stand:    return Blackjack::EActionType::Stand;
            case EBlackjackAction::Double:   return Blackjack::EActionType::Double;
            case EBlackjackAction::Split:    return Blackjack::EActionType::Split;
            case EBlackjackAction::Surrender:return Blackjack::EActionType::Surrender;
            case EBlackjackAction::Insure:   return Blackjack::EActionType::Insure;
            case EBlackjackAction::DeclineInsurance: return Blackjack::EActionType::DeclineInsurance;
            case EBlackjackAction::NewRound: return Blackjack::EActionType::NewRound;
            case EBlackjackAction::SetRuleSet: return Blackjack::EActionType::SetRuleSet;
        }
        return Blackjack::EActionType::Stand;
    }
    FBlackjackHandResult To(const Blackjack::FHandResult& R)
    {
        FBlackjackHandResult Out;
        Out.HandIndex = R.HandIndex;
        Out.Outcome = static_cast<EBlackjackOutcome>(R.Outcome);
        Out.Payout = R.Payout;
        Out.Total = R.Total;
        for (const Blackjack::FCard& C : R.Cards) Out.Cards.Add(To(C));
        Out.Label = R.Label;
        return Out;
    }
}
