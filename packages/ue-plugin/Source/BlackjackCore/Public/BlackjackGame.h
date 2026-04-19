#pragma once

#include "CoreMinimal.h"
#include "BlackjackCards.h"
#include "BlackjackHand.h"
#include "BlackjackRules.h"

namespace Blackjack
{
    enum class EPhase : uint8 { Betting, Dealing, Insurance, PlayerTurn, DealerTurn, Settlement, RoundOver };
    enum class EOutcome : uint8 { Win, Loss, Push, Blackjack, Surrender, Bust };
    enum class EActionType : uint8
    {
        PlaceBet, Deal, Hit, Stand, Double, Split, Surrender, Insure, DeclineInsurance, NewRound, SetRuleSet
    };

    struct FSideBets { int32 PerfectPairs = 0; int32 TwentyOneP3 = 0; int32 LuckyLadies = 0; };

    struct FPlayerHand
    {
        TArray<FCard> Cards;
        int32 Bet = 0;
        bool bDoubled = false;
        bool bSurrendered = false;
        bool bSettled = false;
        bool bStood = false;
        bool bSplitFromAces = false;
    };

    struct FHandResult
    {
        int32 HandIndex;
        EOutcome Outcome;
        int32 Payout;
        int32 Total;
        TArray<FCard> Cards;
        FString Label;
    };

    struct FEngineEvent
    {
        enum class EType : uint8
        {
            PhaseChanged, RuleSetChanged, BetPlaced, CardDealt, HoleCardRevealed,
            PlayerAction, HandBust, NaturalBlackjack, DealerAction, RoundOver,
            BetSettled, BankrollChanged, SideBetWin, ShoeShuffled, Error
        };
        EType Type;
        EPhase Phase = EPhase::Betting;
        ERuleSetId RuleSet = ERuleSetId::Vegas;
        int32 Amount = 0;
        FSideBets SideBetsSnapshot;
        // CardDealt
        bool bToDealer = false;
        int32 HandIndex = 0;
        FCard Card {};
        bool bFaceDown = false;
        // HoleCardRevealed uses Card
        FString ActionName;
        EActionType ActionType = EActionType::Stand;
        int32 DealerTotal = 0;
        bool bDealerSoft = false;
        TArray<FHandResult> RoundResults;
        EOutcome Outcome = EOutcome::Loss;
        int32 Payout = 0;
        int32 Bankroll = 0;
        int32 Delta = 0;
        FString SideBetKind;
        FString Label;
        FString ErrorCode;
        FString ErrorMessage;
    };

    using FEventListener = TFunction<void(const FEngineEvent&)>;

    struct FAction
    {
        EActionType Type;
        int32 Amount = 0;
        FSideBets SideBets;
        ERuleSetId Preset = ERuleSetId::Vegas;
    };

    struct FSnapshot
    {
        EPhase Phase;
        FRuleSet Rules;
        int32 Bankroll;
        TArray<FCard> Dealer;
        bool bDealerHoleHidden;
        TArray<FPlayerHand> Hands;
        int32 ActiveHandIndex;
        int32 PendingBet;
        FSideBets SideBetsSnapshot;
        int32 InsuranceBet;
        TArray<FHandResult> RoundResults;
        TArray<EActionType> LegalActions;
    };

    class BLACKJACKCORE_API FGame
    {
    public:
        FGame(ERuleSetId RuleSetId, uint32 Seed);

        FSnapshot GetState() const;
        TArray<EActionType> GetLegalActions() const;
        void Dispatch(const FAction& Action);
        void SetRuleSet(ERuleSetId Id);
        int32 AddListener(FEventListener L);
        void RemoveListener(int32 Handle);

    private:
        void SetPhase(EPhase P);
        void Emit(const FEngineEvent& E);
        void AdjustBankroll(int32 DeltaAmount);
        FCard DealCardTo(bool bToDealer, int32 HandIndex, bool bFaceDown);
        void PlaceBet(int32 Amount, const FSideBets& Sb);
        void Deal();
        void SettleSideBets();
        void AfterInsurance();
        void RevealHole();
        void Hit();
        void Stand();
        void DoubleDown();
        void Split();
        void Surrender();
        void Insure(int32 Amount);
        void DeclineInsurance();
        void AdvanceHand();
        void DealerTurn();
        void SettleAgainstDealer();
        void NewRound();
        void Err(const FString& Code, const FString& Message);
        double Bonus21Multiplier(const FPlayerHand& H) const;

        FRuleSet Rules;
        FRng Rng;
        FShoe Shoe;
        int32 Bankroll = 0;
        EPhase Phase = EPhase::Betting;
        TArray<FCard> Dealer;
        bool bDealerHoleHidden = true;
        TArray<FPlayerHand> Hands;
        int32 ActiveHandIndex = 0;
        int32 PendingBet = 0;
        FSideBets SideBets;
        int32 InsuranceBet = 0;
        TArray<FHandResult> RoundResults;
        int32 SplitCount = 0;
        int32 NextListenerId = 1;
        TArray<TPair<int32, FEventListener>> Listeners;
    };
}
