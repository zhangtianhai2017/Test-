#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "BlackjackHeatSubsystem.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnBlackjackHeatChanged, int32, NewHeat, int32, Delta);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnBlackjackHeatThresholdCrossed, int32, Threshold);

/**
 * Client-side advisory "heat" tracker for the UE plugin (M7a).
 *
 * Heat is a UX concept: a 0..100 gauge that represents how much scrutiny the
 * pit boss / house is directing at this player. The server will eventually
 * feed authoritative heat values; for v1 this is driven by client heuristics
 * (consecutive wins, oversized bets, camouflage pattern) and UI widgets that
 * call SetHeat / AdjustHeat.
 *
 * The subsystem decays heat by DecayPerSecond each tick (1s interval) and
 * fires OnThresholdCrossed on upward crossings of CrossThresholds.
 */
UCLASS()
class BLACKJACKUE_API UBlackjackHeatSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    /** 0..100. Server may eventually push this; for v1 it's driven by client
     *  heuristics (e.g., consecutive wins, large bets, camouflage pattern). */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category="Blackjack|Heat")
    int32 GetHeat() const { return Heat; }

    UFUNCTION(BlueprintCallable, Category="Blackjack|Heat")
    void SetHeat(int32 NewHeat);

    UFUNCTION(BlueprintCallable, Category="Blackjack|Heat")
    void AdjustHeat(int32 Delta);

    /** Decays heat by DecayPerSecond (default 2) each tick when >0. Called
     *  automatically by the subsystem's timer. Designers can disable. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Blackjack|Heat")
    float DecayPerSecond = 2.f;

    /** Thresholds at which OnThresholdCrossed fires. Default {30, 60, 90}. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Blackjack|Heat")
    TArray<int32> CrossThresholds;

    UPROPERTY(BlueprintAssignable, Category="Blackjack|Heat")
    FOnBlackjackHeatChanged OnHeatChanged;

    UPROPERTY(BlueprintAssignable, Category="Blackjack|Heat")
    FOnBlackjackHeatThresholdCrossed OnThresholdCrossed;

    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

private:
    int32 Heat = 0;
    FTimerHandle DecayTimer;

    void TickDecay();
    void FireCrossings(int32 Old, int32 New);
};
