#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "BlackjackPitBossActor.generated.h"

class USkeletalMeshComponent;

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnBlackjackPitBossArrived);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnBlackjackPitBossDeparted);

/**
 * Actor that represents the pit boss watching the table (M7a).
 *
 * Subscribes to UBlackjackHeatSubsystem::OnHeatChanged. Arrives (becomes
 * visible, collision on, fires OnArrived) when heat crosses ArriveAtHeat
 * upward. Departs (hides, collision off, fires OnDeparted) when heat falls
 * to or below DepartAtHeat. Hysteresis between the two thresholds prevents
 * flicker on small oscillations.
 */
UCLASS(Blueprintable)
class BLACKJACKUE_API ABlackjackPitBossActor : public AActor
{
    GENERATED_BODY()

public:
    ABlackjackPitBossActor();

    /** Heat threshold at which the boss arrives. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Blackjack|PitBoss")
    int32 ArriveAtHeat = 60;

    /** Heat threshold at/below which the boss leaves. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Blackjack|PitBoss")
    int32 DepartAtHeat = 40;

    UPROPERTY(BlueprintReadOnly, Category="Blackjack|PitBoss")
    bool bPresent = false;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Blackjack|PitBoss")
    USkeletalMeshComponent* MeshComponent;

    UPROPERTY(BlueprintAssignable, Category="Blackjack|PitBoss")
    FOnBlackjackPitBossArrived OnArrived;

    UPROPERTY(BlueprintAssignable, Category="Blackjack|PitBoss")
    FOnBlackjackPitBossDeparted OnDeparted;

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;

    UFUNCTION()
    void HandleHeatChanged(int32 NewHeat, int32 Delta);

    void SetPresent(bool bNew);
};
