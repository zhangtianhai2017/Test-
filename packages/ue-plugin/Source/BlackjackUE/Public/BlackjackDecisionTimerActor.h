#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "BlackjackDecisionTimerActor.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnBlackjackDecisionTimerStart, float, DurationSeconds);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnBlackjackDecisionTimerTick, float, SecondsRemaining);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnBlackjackDecisionTimerExpire);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnBlackjackDecisionTimerCancel);

/**
 * Drop into the level. Designers bind StartTimer() to the moment it becomes
 * the local player's turn (typically from UBlackjackNetClient::OnPhaseChanged
 * hitting "playerTurn" for a seat you own). Fires Tick every 0.1s + Expire
 * when it hits 0 so the UI can show a countdown.
 */
UCLASS(Blueprintable)
class BLACKJACKUE_API ABlackjackDecisionTimerActor : public AActor
{
    GENERATED_BODY()
public:
    ABlackjackDecisionTimerActor();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Blackjack|Timer")
    float DefaultDurationSeconds = 20.f;

    UFUNCTION(BlueprintCallable, Category="Blackjack|Timer")
    void StartTimer(float DurationSeconds = 0.f);

    UFUNCTION(BlueprintCallable, Category="Blackjack|Timer")
    void CancelTimer();

    UFUNCTION(BlueprintCallable, BlueprintPure, Category="Blackjack|Timer")
    bool IsRunning() const { return bRunning; }

    UFUNCTION(BlueprintCallable, BlueprintPure, Category="Blackjack|Timer")
    float GetSecondsRemaining() const { return RemainingSeconds; }

    UPROPERTY(BlueprintAssignable, Category="Blackjack|Timer")
    FOnBlackjackDecisionTimerStart  OnTimerStart;
    UPROPERTY(BlueprintAssignable, Category="Blackjack|Timer")
    FOnBlackjackDecisionTimerTick   OnTimerTick;
    UPROPERTY(BlueprintAssignable, Category="Blackjack|Timer")
    FOnBlackjackDecisionTimerExpire OnTimerExpire;
    UPROPERTY(BlueprintAssignable, Category="Blackjack|Timer")
    FOnBlackjackDecisionTimerCancel OnTimerCancel;

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;

    void TickImpl();

private:
    FTimerHandle TickHandle;
    float RemainingSeconds = 0.f;
    bool bRunning = false;
};
