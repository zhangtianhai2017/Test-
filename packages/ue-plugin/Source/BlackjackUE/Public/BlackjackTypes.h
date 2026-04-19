#pragma once

#include "CoreMinimal.h"
#include "BlackjackCards.h"
#include "BlackjackGame.h"
#include "BlackjackRules.h"
#include "BlackjackTypes.generated.h"

UENUM(BlueprintType)
enum class EBlackjackSuit : uint8 { Spades, Hearts, Diamonds, Clubs };

UENUM(BlueprintType)
enum class EBlackjackRank : uint8 { Ace, Two, Three, Four, Five, Six, Seven, Eight, Nine, Ten, Jack, Queen, King };

UENUM(BlueprintType)
enum class EBlackjackRuleSet : uint8 { Vegas, Spanish21, Pontoon, SuperFun21 };

UENUM(BlueprintType)
enum class EBlackjackPhase : uint8 { Betting, Dealing, Insurance, PlayerTurn, DealerTurn, Settlement, RoundOver };

UENUM(BlueprintType)
enum class EBlackjackOutcome : uint8 { Win, Loss, Push, Blackjack, Surrender, Bust };

UENUM(BlueprintType)
enum class EBlackjackAction : uint8 { PlaceBet, Hit, Stand, Double, Split, Surrender, Insure, DeclineInsurance, NewRound, SetRuleSet };

UENUM(BlueprintType)
enum class EBlackjackTarget : uint8 { Player, Dealer };

UENUM(BlueprintType)
enum class EBlackjackSideBet : uint8 { PerfectPairs, TwentyOneP3, LuckyLadies };

USTRUCT(BlueprintType)
struct FBlackjackCard
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) EBlackjackRank Rank = EBlackjackRank::Ace;
    UPROPERTY(BlueprintReadOnly) EBlackjackSuit Suit = EBlackjackSuit::Spades;
};

USTRUCT(BlueprintType)
struct FBlackjackSideBets
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 PerfectPairs = 0;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 TwentyOneP3 = 0;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 LuckyLadies = 0;
};

USTRUCT(BlueprintType)
struct FBlackjackHandResult
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) int32 HandIndex = 0;
    UPROPERTY(BlueprintReadOnly) EBlackjackOutcome Outcome = EBlackjackOutcome::Loss;
    UPROPERTY(BlueprintReadOnly) int32 Payout = 0;
    UPROPERTY(BlueprintReadOnly) int32 Total = 0;
    UPROPERTY(BlueprintReadOnly) TArray<FBlackjackCard> Cards;
    UPROPERTY(BlueprintReadOnly) FString Label;
};

USTRUCT(BlueprintType)
struct FBlackjackStateSnapshot
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly) EBlackjackPhase Phase = EBlackjackPhase::Betting;
    UPROPERTY(BlueprintReadOnly) EBlackjackRuleSet RuleSet = EBlackjackRuleSet::Vegas;
    UPROPERTY(BlueprintReadOnly) int32 Bankroll = 0;
    UPROPERTY(BlueprintReadOnly) TArray<FBlackjackCard> Dealer;
    UPROPERTY(BlueprintReadOnly) bool bDealerHoleHidden = true;
    UPROPERTY(BlueprintReadOnly) int32 ActiveHandIndex = 0;
    UPROPERTY(BlueprintReadOnly) TArray<FBlackjackHandResult> RoundResults;
};

namespace BlackjackConv
{
    BLACKJACKUE_API FBlackjackCard To(const Blackjack::FCard& C);
    BLACKJACKUE_API Blackjack::FCard From(const FBlackjackCard& C);
    BLACKJACKUE_API EBlackjackRuleSet To(Blackjack::ERuleSetId R);
    BLACKJACKUE_API Blackjack::ERuleSetId From(EBlackjackRuleSet R);
    BLACKJACKUE_API EBlackjackPhase To(Blackjack::EPhase P);
    BLACKJACKUE_API EBlackjackOutcome To(Blackjack::EOutcome O);
    BLACKJACKUE_API EBlackjackAction To(Blackjack::EActionType A);
    BLACKJACKUE_API Blackjack::EActionType From(EBlackjackAction A);
    BLACKJACKUE_API FBlackjackHandResult To(const Blackjack::FHandResult& R);
}
