#include "BlackjackGame.h"
#include "BlackjackDealer.h"
#include "BlackjackSideBets.h"

namespace Blackjack
{
    FGame::FGame(ERuleSetId RuleSetId, uint32 Seed)
        : Rules(GetPreset(RuleSetId))
        , Rng(Seed)
        , Shoe(Rng, Rules.Decks, Rules.Penetration, Rules.bRemoveTens)
        , Bankroll(Rules.StartingBankroll)
    {
    }

    int32 FGame::AddListener(FEventListener L)
    {
        const int32 Id = NextListenerId++;
        Listeners.Add({ Id, MoveTemp(L) });
        return Id;
    }

    void FGame::RemoveListener(int32 Handle)
    {
        Listeners.RemoveAll([Handle](const TPair<int32, FEventListener>& P) { return P.Key == Handle; });
    }

    void FGame::Emit(const FEngineEvent& E)
    {
        for (const auto& P : Listeners) P.Value(E);
    }

    void FGame::SetPhase(EPhase P)
    {
        if (Phase != P)
        {
            Phase = P;
            FEngineEvent E;
            E.Type = FEngineEvent::EType::PhaseChanged;
            E.Phase = P;
            Emit(E);
        }
    }

    void FGame::AdjustBankroll(int32 DeltaAmount)
    {
        Bankroll += DeltaAmount;
        FEngineEvent E;
        E.Type = FEngineEvent::EType::BankrollChanged;
        E.Bankroll = Bankroll;
        E.Delta = DeltaAmount;
        Emit(E);
    }

    FCard FGame::DealCardTo(bool bToDealer, int32 HandIndex, bool bFaceDown)
    {
        FCard C = Shoe.Draw();
        if (bToDealer) Dealer.Add(C);
        else Hands[HandIndex].Cards.Add(C);
        FEngineEvent E;
        E.Type = FEngineEvent::EType::CardDealt;
        E.bToDealer = bToDealer;
        E.HandIndex = HandIndex;
        E.Card = C;
        E.bFaceDown = bFaceDown;
        Emit(E);
        return C;
    }

    void FGame::Err(const FString& Code, const FString& Message)
    {
        FEngineEvent E;
        E.Type = FEngineEvent::EType::Error;
        E.ErrorCode = Code;
        E.ErrorMessage = Message;
        Emit(E);
    }

    void FGame::PlaceBet(int32 Amount, const FSideBets& Sb)
    {
        if (Phase != EPhase::Betting) { Err(TEXT("ILLEGAL_ACTION"), TEXT("Not in betting phase")); return; }
        if (Amount < Rules.MinBet || Amount > Rules.MaxBet)
        {
            Err(TEXT("BET_OUT_OF_RANGE"), FString::Printf(TEXT("bet must be %d-%d"), Rules.MinBet, Rules.MaxBet));
            return;
        }
        const int32 SbAmt = Sb.PerfectPairs + Sb.TwentyOneP3 + Sb.LuckyLadies;
        if (Amount + SbAmt > Bankroll) { Err(TEXT("INSUFFICIENT_FUNDS"), TEXT("Not enough bankroll")); return; }
        PendingBet = Amount;
        SideBets = Sb;
        AdjustBankroll(-(Amount + SbAmt));
        FEngineEvent E;
        E.Type = FEngineEvent::EType::BetPlaced;
        E.Amount = Amount;
        E.SideBetsSnapshot = Sb;
        Emit(E);
        Deal();
    }

    void FGame::Deal()
    {
        SetPhase(EPhase::Dealing);
        Hands.Reset();
        FPlayerHand H0;
        H0.Bet = PendingBet;
        Hands.Add(H0);
        Dealer.Reset();
        bDealerHoleHidden = true;
        SplitCount = 0;
        ActiveHandIndex = 0;

        DealCardTo(false, 0, false);
        DealCardTo(true,  0, false);
        DealCardTo(false, 0, false);
        DealCardTo(true,  0, true);

        SettleSideBets();

        if (Rules.bDealerPeeksOnAce && Dealer[0].Rank == ERank::Ace) { SetPhase(EPhase::Insurance); return; }
        AfterInsurance();
    }

    void FGame::SettleSideBets()
    {
        const TArray<FCard>& P = Hands[0].Cards;
        auto EmitWin = [this](const FString& Kind, int32 Payout, const FString& Label)
        {
            FEngineEvent E;
            E.Type = FEngineEvent::EType::SideBetWin;
            E.SideBetKind = Kind;
            E.Payout = Payout;
            E.Label = Label;
            Emit(E);
        };

        if (SideBets.PerfectPairs > 0)
        {
            const FSideBetResult R = EvalPerfectPairs(P);
            if (R.Payout > 0)
            {
                const int32 Pay = SideBets.PerfectPairs * (R.Payout + 1);
                AdjustBankroll(Pay);
                EmitWin(TEXT("perfectPairs"), Pay, R.Label);
            }
        }
        if (SideBets.TwentyOneP3 > 0)
        {
            const FSideBetResult R = EvalTwentyOnePlusThree(P, Dealer[0], Dealer.Num() > 0);
            if (R.Payout > 0)
            {
                const int32 Pay = SideBets.TwentyOneP3 * (R.Payout + 1);
                AdjustBankroll(Pay);
                EmitWin(TEXT("21+3"), Pay, R.Label);
            }
        }
        if (SideBets.LuckyLadies > 0)
        {
            const FSideBetResult R = EvalLuckyLadies(P, Dealer);
            if (R.Payout > 0)
            {
                const int32 Pay = SideBets.LuckyLadies * (R.Payout + 1);
                AdjustBankroll(Pay);
                EmitWin(TEXT("luckyLadies"), Pay, R.Label);
            }
        }
    }

    void FGame::AfterInsurance()
    {
        const bool bDealerBJ = IsBlackjack(Dealer);
        if (bDealerBJ && (Rules.bDealerPeeksOnAce || Rules.bDealerPeeksOnTen))
        {
            const bool bUpIsTen = RankValue(Dealer[0].Rank) == 10;
            const bool bUpIsAce = Dealer[0].Rank == ERank::Ace;
            if ((bUpIsAce && Rules.bDealerPeeksOnAce) || (bUpIsTen && Rules.bDealerPeeksOnTen))
            {
                RevealHole();
                SettleAgainstDealer();
                return;
            }
        }
        if (IsBlackjack(Hands[0].Cards))
        {
            FEngineEvent E;
            E.Type = FEngineEvent::EType::NaturalBlackjack;
            E.HandIndex = 0;
            Emit(E);
            RevealHole();
            SettleAgainstDealer();
            return;
        }
        SetPhase(EPhase::PlayerTurn);
    }

    void FGame::RevealHole()
    {
        bDealerHoleHidden = false;
        if (Dealer.Num() >= 2)
        {
            FEngineEvent E;
            E.Type = FEngineEvent::EType::HoleCardRevealed;
            E.Card = Dealer[1];
            Emit(E);
        }
    }

    void FGame::Hit()
    {
        if (!Hands.IsValidIndex(ActiveHandIndex)) return;
        FPlayerHand& H = Hands[ActiveHandIndex];
        FEngineEvent E;
        E.Type = FEngineEvent::EType::PlayerAction;
        E.ActionName = TEXT("HIT");
        E.HandIndex = ActiveHandIndex;
        Emit(E);
        DealCardTo(false, ActiveHandIndex, false);
        const FHandValue V = Evaluate(H.Cards);
        if (Rules.Id == ERuleSetId::Pontoon && H.Cards.Num() >= 5 && !V.bBust)
        {
            H.bStood = true;
            AdvanceHand();
            return;
        }
        if (V.bBust)
        {
            FEngineEvent B;
            B.Type = FEngineEvent::EType::HandBust;
            B.HandIndex = ActiveHandIndex;
            Emit(B);
            AdvanceHand();
        }
        else if (V.Total == 21)
        {
            H.bStood = true;
            AdvanceHand();
        }
    }

    void FGame::Stand()
    {
        if (!Hands.IsValidIndex(ActiveHandIndex)) return;
        FEngineEvent E;
        E.Type = FEngineEvent::EType::PlayerAction;
        E.ActionName = TEXT("STAND");
        E.HandIndex = ActiveHandIndex;
        Emit(E);
        Hands[ActiveHandIndex].bStood = true;
        AdvanceHand();
    }

    void FGame::DoubleDown()
    {
        if (!Hands.IsValidIndex(ActiveHandIndex)) return;
        FPlayerHand& H = Hands[ActiveHandIndex];
        if (H.Cards.Num() != 2) { Err(TEXT("ILLEGAL_ACTION"), TEXT("Double requires 2 cards")); return; }
        if (Bankroll < H.Bet) { Err(TEXT("INSUFFICIENT_FUNDS"), TEXT("Cannot cover double")); return; }
        AdjustBankroll(-H.Bet);
        H.Bet *= 2;
        H.bDoubled = true;
        FEngineEvent E;
        E.Type = FEngineEvent::EType::PlayerAction;
        E.ActionName = TEXT("DOUBLE");
        E.HandIndex = ActiveHandIndex;
        Emit(E);
        DealCardTo(false, ActiveHandIndex, false);
        H.bStood = true;
        const FHandValue V = Evaluate(H.Cards);
        if (V.bBust)
        {
            FEngineEvent B;
            B.Type = FEngineEvent::EType::HandBust;
            B.HandIndex = ActiveHandIndex;
            Emit(B);
        }
        AdvanceHand();
    }

    void FGame::Split()
    {
        if (!Hands.IsValidIndex(ActiveHandIndex)) return;
        FPlayerHand& H = Hands[ActiveHandIndex];
        if (!IsPair(H.Cards)) { Err(TEXT("ILLEGAL_ACTION"), TEXT("Not a pair")); return; }
        if (SplitCount >= Rules.MaxSplits) { Err(TEXT("ILLEGAL_ACTION"), TEXT("Max splits reached")); return; }
        if (Bankroll < H.Bet) { Err(TEXT("INSUFFICIENT_FUNDS"), TEXT("Cannot cover split")); return; }
        const bool bIsAces = H.Cards[0].Rank == ERank::Ace;
        AdjustBankroll(-H.Bet);
        ++SplitCount;
        const FCard Second = H.Cards.Pop();
        FPlayerHand NewHand;
        NewHand.Cards.Add(Second);
        NewHand.Bet = H.Bet;
        NewHand.bSplitFromAces = bIsAces;
        H.bSplitFromAces = bIsAces;
        Hands.Insert(NewHand, ActiveHandIndex + 1);
        FEngineEvent E;
        E.Type = FEngineEvent::EType::PlayerAction;
        E.ActionName = TEXT("SPLIT");
        E.HandIndex = ActiveHandIndex;
        Emit(E);
        DealCardTo(false, ActiveHandIndex, false);
        DealCardTo(false, ActiveHandIndex + 1, false);
        if (bIsAces && Rules.bSplitAcesOneCardOnly)
        {
            Hands[ActiveHandIndex].bStood = true;
            Hands[ActiveHandIndex + 1].bStood = true;
            AdvanceHand();
        }
    }

    void FGame::Surrender()
    {
        if (!Hands.IsValidIndex(ActiveHandIndex)) return;
        FPlayerHand& H = Hands[ActiveHandIndex];
        if (!Rules.bAllowSurrender || Hands.Num() != 1 || H.Cards.Num() != 2)
        {
            Err(TEXT("ILLEGAL_ACTION"), TEXT("Surrender not allowed"));
            return;
        }
        H.bSurrendered = true;
        H.bStood = true;
        FEngineEvent E;
        E.Type = FEngineEvent::EType::PlayerAction;
        E.ActionName = TEXT("SURRENDER");
        E.HandIndex = ActiveHandIndex;
        Emit(E);
        AdvanceHand();
    }

    void FGame::Insure(int32 Amount)
    {
        if (Phase != EPhase::Insurance) { Err(TEXT("ILLEGAL_ACTION"), TEXT("Not in insurance phase")); return; }
        const int32 MaxAmt = Hands[0].Bet / 2;
        if (Amount < 0 || Amount > MaxAmt) { Err(TEXT("BET_OUT_OF_RANGE"), FString::Printf(TEXT("0-%d"), MaxAmt)); return; }
        if (Amount > Bankroll) { Err(TEXT("INSUFFICIENT_FUNDS"), TEXT("Not enough bankroll")); return; }
        InsuranceBet = Amount;
        AdjustBankroll(-Amount);
        AfterInsurance();
    }

    void FGame::DeclineInsurance()
    {
        if (Phase != EPhase::Insurance) { Err(TEXT("ILLEGAL_ACTION"), TEXT("Not in insurance phase")); return; }
        InsuranceBet = 0;
        AfterInsurance();
    }

    void FGame::AdvanceHand()
    {
        while (ActiveHandIndex < Hands.Num())
        {
            FPlayerHand& H = Hands[ActiveHandIndex];
            const FHandValue V = Evaluate(H.Cards);
            if (H.bStood || H.bSurrendered || V.bBust) { ++ActiveHandIndex; continue; }
            return;
        }
        DealerTurn();
    }

    void FGame::DealerTurn()
    {
        SetPhase(EPhase::DealerTurn);
        RevealHole();
        bool bAnyLive = false;
        for (const FPlayerHand& H : Hands)
        {
            if (!H.bSurrendered && !Evaluate(H.Cards).bBust) { bAnyLive = true; break; }
        }
        if (bAnyLive)
        {
            while (DealerShouldHit(Dealer, Rules))
            {
                FCard C = Shoe.Draw();
                Dealer.Add(C);
                const FHandValue V = Evaluate(Dealer);
                FEngineEvent D;
                D.Type = FEngineEvent::EType::DealerAction;
                D.ActionName = TEXT("HIT");
                D.DealerTotal = V.Total;
                D.bDealerSoft = V.bSoft;
                Emit(D);
                FEngineEvent CE;
                CE.Type = FEngineEvent::EType::CardDealt;
                CE.bToDealer = true;
                CE.HandIndex = 0;
                CE.Card = C;
                CE.bFaceDown = false;
                Emit(CE);
            }
            const FHandValue V = Evaluate(Dealer);
            FEngineEvent S;
            S.Type = FEngineEvent::EType::DealerAction;
            S.ActionName = TEXT("STAND");
            S.DealerTotal = V.Total;
            S.bDealerSoft = V.bSoft;
            Emit(S);
        }
        SettleAgainstDealer();
    }

    double FGame::Bonus21Multiplier(const FPlayerHand& H) const
    {
        if (!Rules.bBonus21s) return 0.0;
        const FHandValue V = Evaluate(H.Cards);
        if (V.Total != 21 || H.Cards.Num() < 5) return 0.0;
        const int32 Len = H.Cards.Num();
        bool bSuited = true;
        for (const FCard& C : H.Cards) if (C.Suit != H.Cards[0].Suit) { bSuited = false; break; }
        if (Len == 5) return bSuited ? 1.5 : 0.5;
        if (Len == 6) return bSuited ? 2.0 : 1.0;
        return bSuited ? 3.0 : 2.0;
    }

    void FGame::SettleAgainstDealer()
    {
        SetPhase(EPhase::Settlement);
        const FHandValue Dv = Evaluate(Dealer);
        const bool bDealerBJ = IsBlackjack(Dealer);
        const int32 InsPayout = (bDealerBJ && InsuranceBet > 0) ? static_cast<int32>(InsuranceBet * (Rules.InsurancePays + 1.0)) : 0;
        if (InsPayout > 0) AdjustBankroll(InsPayout);

        for (int32 I = 0; I < Hands.Num(); ++I)
        {
            FPlayerHand& H = Hands[I];
            const FHandValue V = Evaluate(H.Cards);
            EOutcome Outcome = EOutcome::Loss;
            int32 Payout = 0;
            FString Label;

            if (H.bSurrendered)
            {
                Outcome = EOutcome::Surrender;
                Payout = H.Bet / 2;
            }
            else if (V.bBust)
            {
                Outcome = EOutcome::Bust;
                Payout = 0;
            }
            else if (IsBlackjack(H.Cards) && !H.bSplitFromAces)
            {
                if (bDealerBJ) { Outcome = EOutcome::Push; Payout = H.Bet; }
                else
                {
                    Outcome = EOutcome::Blackjack;
                    Payout = static_cast<int32>(H.Bet * (1.0 + Rules.BlackjackPays));
                }
            }
            else
            {
                const double BonusMult = Bonus21Multiplier(H);
                if (bDealerBJ) Outcome = EOutcome::Loss;
                else if (Dv.bBust) { Outcome = EOutcome::Win; Payout = H.Bet * 2; }
                else if (V.Total > Dv.Total) { Outcome = EOutcome::Win; Payout = H.Bet * 2; }
                else if (V.Total < Dv.Total) { Outcome = EOutcome::Loss; }
                else { Outcome = EOutcome::Push; Payout = H.Bet; }

                if (BonusMult > 0.0 && Outcome == EOutcome::Win)
                {
                    const int32 Bonus = static_cast<int32>(H.Bet * BonusMult);
                    Payout += Bonus;
                    Label = FString::Printf(TEXT("Bonus 21 +%d"), Bonus);
                }
                if (Rules.bPlayerTotalsWinOver17 && Outcome == EOutcome::Loss && V.Total >= 17 && V.Total <= 21 && !bDealerBJ && !V.bBust && V.Total > Dv.Total)
                {
                    Outcome = EOutcome::Win;
                    Payout = H.Bet * 2;
                }
            }

            if (Payout > 0) AdjustBankroll(Payout);
            FHandResult R;
            R.HandIndex = I;
            R.Outcome = Outcome;
            R.Payout = Payout;
            R.Total = V.Total;
            R.Cards = H.Cards;
            R.Label = Label;
            RoundResults.Add(R);

            FEngineEvent E;
            E.Type = FEngineEvent::EType::BetSettled;
            E.HandIndex = I;
            E.Outcome = Outcome;
            E.Payout = Payout;
            Emit(E);
        }

        FEngineEvent E;
        E.Type = FEngineEvent::EType::RoundOver;
        E.RoundResults = RoundResults;
        Emit(E);
        SetPhase(EPhase::RoundOver);
        if (Shoe.NeedsShuffle())
        {
            Shoe.Reshuffle();
            FEngineEvent S;
            S.Type = FEngineEvent::EType::ShoeShuffled;
            Emit(S);
        }
    }

    void FGame::NewRound()
    {
        PendingBet = 0;
        SideBets = FSideBets();
        InsuranceBet = 0;
        Hands.Reset();
        Dealer.Reset();
        bDealerHoleHidden = true;
        RoundResults.Reset();
        ActiveHandIndex = 0;
        SetPhase(EPhase::Betting);
    }

    void FGame::SetRuleSet(ERuleSetId Id)
    {
        Rules = GetPreset(Id);
        Shoe = FShoe(Rng, Rules.Decks, Rules.Penetration, Rules.bRemoveTens);
        FEngineEvent E;
        E.Type = FEngineEvent::EType::RuleSetChanged;
        E.RuleSet = Id;
        Emit(E);
        NewRound();
    }

    TArray<EActionType> FGame::GetLegalActions() const
    {
        TArray<EActionType> Out;
        if (Phase == EPhase::Betting) { Out = { EActionType::PlaceBet, EActionType::SetRuleSet }; return Out; }
        if (Phase == EPhase::Insurance) { Out = { EActionType::Insure, EActionType::DeclineInsurance }; return Out; }
        if (Phase == EPhase::PlayerTurn)
        {
            if (!Hands.IsValidIndex(ActiveHandIndex)) return Out;
            const FPlayerHand& H = Hands[ActiveHandIndex];
            Out.Add(EActionType::Hit);
            Out.Add(EActionType::Stand);
            if (H.Cards.Num() == 2 && !H.bSplitFromAces)
            {
                Out.Add(EActionType::Double);
                if (IsPair(H.Cards) && SplitCount < Rules.MaxSplits) Out.Add(EActionType::Split);
                if (Rules.bAllowSurrender && Hands.Num() == 1) Out.Add(EActionType::Surrender);
            }
            return Out;
        }
        if (Phase == EPhase::RoundOver) { Out = { EActionType::NewRound, EActionType::SetRuleSet }; return Out; }
        return Out;
    }

    FSnapshot FGame::GetState() const
    {
        FSnapshot S;
        S.Phase = Phase;
        S.Rules = Rules;
        S.Bankroll = Bankroll;
        S.Dealer = Dealer;
        S.bDealerHoleHidden = bDealerHoleHidden;
        S.Hands = Hands;
        S.ActiveHandIndex = ActiveHandIndex;
        S.PendingBet = PendingBet;
        S.SideBetsSnapshot = SideBets;
        S.InsuranceBet = InsuranceBet;
        S.RoundResults = RoundResults;
        S.LegalActions = GetLegalActions();
        return S;
    }

    void FGame::Dispatch(const FAction& A)
    {
        switch (A.Type)
        {
            case EActionType::PlaceBet: PlaceBet(A.Amount, A.SideBets); break;
            case EActionType::Hit: if (Phase == EPhase::PlayerTurn) Hit(); else Err(TEXT("ILLEGAL_ACTION"), TEXT("HIT")); break;
            case EActionType::Stand: if (Phase == EPhase::PlayerTurn) Stand(); else Err(TEXT("ILLEGAL_ACTION"), TEXT("STAND")); break;
            case EActionType::Double: if (Phase == EPhase::PlayerTurn) DoubleDown(); else Err(TEXT("ILLEGAL_ACTION"), TEXT("DOUBLE")); break;
            case EActionType::Split: if (Phase == EPhase::PlayerTurn) Split(); else Err(TEXT("ILLEGAL_ACTION"), TEXT("SPLIT")); break;
            case EActionType::Surrender: if (Phase == EPhase::PlayerTurn) Surrender(); else Err(TEXT("ILLEGAL_ACTION"), TEXT("SURRENDER")); break;
            case EActionType::Insure: Insure(A.Amount); break;
            case EActionType::DeclineInsurance: DeclineInsurance(); break;
            case EActionType::NewRound: if (Phase == EPhase::RoundOver) NewRound(); else Err(TEXT("ILLEGAL_ACTION"), TEXT("NEW_ROUND")); break;
            case EActionType::SetRuleSet: SetRuleSet(A.Preset); break;
            case EActionType::Deal: Err(TEXT("INTERNAL"), TEXT("DEAL is automatic")); break;
        }
    }
}
