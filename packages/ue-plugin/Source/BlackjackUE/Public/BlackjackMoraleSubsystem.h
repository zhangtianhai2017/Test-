#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "BlackjackMoraleSubsystem.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnBlackjackMoraleChanged, float, NewMorale, float, Delta);

/**
 * Client-side morale tracker (M7a).
 *
 * Morale is a 0.0..1.0 gauge representing the player's mental state —
 * higher values indicate a calmer, more composed player. Client code feeds
 * the subsystem via SetMorale / AdjustMorale in response to wins, losses,
 * losing streaks, dealer taunts, etc. The subsystem regresses morale toward
 * the 0.5 neutral value at RegressionPerSecond on a 1s timer.
 */
UCLASS()
class BLACKJACKUE_API UBlackjackMoraleSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    /** 0.0..1.0. Represents the player's mental state — higher is calmer. */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category="Blackjack|Morale")
    float GetMorale() const { return Morale; }

    UFUNCTION(BlueprintCallable, Category="Blackjack|Morale")
    void SetMorale(float NewMorale);

    UFUNCTION(BlueprintCallable, Category="Blackjack|Morale")
    void AdjustMorale(float Delta);

    /** Morale drifts toward 0.5 neutral when no events happen, rate of
     *  RegressionPerSecond (default 0.05). */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Blackjack|Morale")
    float RegressionPerSecond = 0.05f;

    UPROPERTY(BlueprintAssignable, Category="Blackjack|Morale")
    FOnBlackjackMoraleChanged OnMoraleChanged;

    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

private:
    float Morale = 0.75f;
    FTimerHandle RegressTimer;

    void TickRegression();
};
