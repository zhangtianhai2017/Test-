// Pure-C++ pawn for the Blackjack sample.
// A static ADefaultPawn subclass whose only job is to host a UCameraComponent
// looking down at the table. No movement, no .uasset — all code. Validated for UE 5.6.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/DefaultPawn.h"
#include "BlackjackSamplePawn.generated.h"

class UCameraComponent;

UCLASS()
class BLACKJACKSAMPLE_API ABlackjackSamplePawn : public ADefaultPawn
{
    GENERATED_BODY()

public:
    ABlackjackSamplePawn();

    /** Camera looking down at the felt from a fixed vantage. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Blackjack|Camera")
    UCameraComponent* TableCamera = nullptr;
};
