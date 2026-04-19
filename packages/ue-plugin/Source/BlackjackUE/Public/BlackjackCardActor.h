#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "BlackjackTypes.h"
#include "BlackjackCardActor.generated.h"

class UStaticMeshComponent;

UCLASS(Blueprintable)
class BLACKJACKUE_API ABlackjackCardActor : public AActor
{
    GENERATED_BODY()

public:
    ABlackjackCardActor();

    /** Placeholder cube mesh scaled to card proportions. Override the Static Mesh asset in a BP to use a real card model. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly) UStaticMeshComponent* CardMesh;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Blackjack") FBlackjackCard Card;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack") bool bFaceDown = false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack") FVector TargetLocation = FVector::ZeroVector;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack") FRotator TargetRotation = FRotator::ZeroRotator;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack") float DealDuration = 0.4f;

    UFUNCTION(BlueprintCallable, Category = "Blackjack")
    void InitializeCard(const FBlackjackCard& InCard, bool bInFaceDown);

    UFUNCTION(BlueprintCallable, Category = "Blackjack")
    void FlipFaceUp();

    /** Override in a Blueprint child to drive animation/sequencer (placeholder just tweens to target). */
    UFUNCTION(BlueprintNativeEvent, Category = "Blackjack")
    void PlayDealAnimation(FVector FromLocation, FVector ToLocation, FRotator ToRotation);

protected:
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;

private:
    FVector FromLoc;
    float Elapsed = 0.f;
    bool bTweening = false;
};
