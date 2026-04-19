#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "BlackjackTypes.h"
#include "BlackjackGameComponent.generated.h"

namespace Blackjack { class FGame; }

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FBlackjackOnPhaseChanged, EBlackjackPhase, NewPhase);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_FourParams(FBlackjackOnCardDealt, EBlackjackTarget, To, int32, HandIndex, FBlackjackCard, Card, bool, bFaceDown);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FBlackjackOnHoleCardRevealed, FBlackjackCard, Card);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FBlackjackOnPlayerAction, EBlackjackAction, Action, int32, HandIndex);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FBlackjackOnHandBust, int32, HandIndex);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FBlackjackOnNaturalBlackjack, int32, HandIndex);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FBlackjackOnRoundOver, const TArray<FBlackjackHandResult>&, Results);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FBlackjackOnBetSettled, int32, HandIndex, EBlackjackOutcome, Outcome, int32, Payout);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FBlackjackOnBankrollChanged, int32, NewBankroll, int32, Delta);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FBlackjackOnBigWin, int32, Amount);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FBlackjackOnBankrupt);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FBlackjackOnSideBetWin, EBlackjackSideBet, Kind, int32, Payout, const FString&, Label);

UCLASS(ClassGroup = (Blackjack), meta = (BlueprintSpawnableComponent))
class BLACKJACKUE_API UBlackjackGameComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UBlackjackGameComponent();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack")
    EBlackjackRuleSet RuleSet = EBlackjackRuleSet::Vegas;

    /** 0 = use engine time as seed (non-deterministic). Any non-zero seeds the mulberry32 RNG identically to the TS engine. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack")
    int32 Seed = 0;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack")
    int32 BigWinThreshold = 250;

    UPROPERTY(BlueprintAssignable) FBlackjackOnPhaseChanged OnPhaseChanged;
    UPROPERTY(BlueprintAssignable) FBlackjackOnCardDealt OnCardDealt;
    UPROPERTY(BlueprintAssignable) FBlackjackOnHoleCardRevealed OnHoleCardRevealed;
    UPROPERTY(BlueprintAssignable) FBlackjackOnPlayerAction OnPlayerAction;
    UPROPERTY(BlueprintAssignable) FBlackjackOnHandBust OnHandBust;
    UPROPERTY(BlueprintAssignable) FBlackjackOnNaturalBlackjack OnNaturalBlackjack;
    UPROPERTY(BlueprintAssignable) FBlackjackOnRoundOver OnRoundOver;
    UPROPERTY(BlueprintAssignable) FBlackjackOnBetSettled OnBetSettled;
    UPROPERTY(BlueprintAssignable) FBlackjackOnBankrollChanged OnBankrollChanged;
    UPROPERTY(BlueprintAssignable) FBlackjackOnBigWin OnBigWin;
    UPROPERTY(BlueprintAssignable) FBlackjackOnBankrupt OnBankrupt;
    UPROPERTY(BlueprintAssignable) FBlackjackOnSideBetWin OnSideBetWin;

    UFUNCTION(BlueprintCallable, Category = "Blackjack")
    void PlaceBet(int32 Amount, FBlackjackSideBets SideBets);

    UFUNCTION(BlueprintCallable, Category = "Blackjack") void Hit();
    UFUNCTION(BlueprintCallable, Category = "Blackjack") void Stand();
    UFUNCTION(BlueprintCallable, Category = "Blackjack") void Double();
    UFUNCTION(BlueprintCallable, Category = "Blackjack") void Split();
    UFUNCTION(BlueprintCallable, Category = "Blackjack") void Surrender();
    UFUNCTION(BlueprintCallable, Category = "Blackjack") void Insure(int32 Amount);
    UFUNCTION(BlueprintCallable, Category = "Blackjack") void DeclineInsurance();
    UFUNCTION(BlueprintCallable, Category = "Blackjack") void NewRound();
    UFUNCTION(BlueprintCallable, Category = "Blackjack") void SetRuleSetAsset(EBlackjackRuleSet NewRuleSet);

    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "Blackjack")
    FBlackjackStateSnapshot GetSnapshot() const;

    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "Blackjack")
    TArray<EBlackjackAction> GetLegalActions() const;

    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "Blackjack")
    int32 GetBankroll() const;

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;

private:
    TUniquePtr<Blackjack::FGame> Game;
    int32 ListenerHandle = 0;
    int32 PreviousBankroll = 0;
    void EnsureGame();
    void HandleEngineEvent(const Blackjack::FEngineEvent& E);
};
