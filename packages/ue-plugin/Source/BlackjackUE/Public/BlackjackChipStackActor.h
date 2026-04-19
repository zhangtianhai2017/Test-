#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "BlackjackChipStackActor.generated.h"

class UInstancedStaticMeshComponent;

UCLASS(Blueprintable)
class BLACKJACKUE_API ABlackjackChipStackActor : public AActor
{
    GENERATED_BODY()

public:
    ABlackjackChipStackActor();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly) UInstancedStaticMeshComponent* ChipInstances;

    /** Visual chip count; one instance per unit. Scaled by BP for aesthetics. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack") int32 ChipCount = 0;

    UFUNCTION(BlueprintCallable, Category = "Blackjack")
    void SetChipCount(int32 NewCount);

protected:
    virtual void OnConstruction(const FTransform& Transform) override;

private:
    void RebuildInstances();
};
