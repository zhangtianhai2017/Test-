#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "BlackjackPerceptionWiring.generated.h"

/**
 * Designer-friendly installer that wires the client-side perception
 * subsystems (UBlackjackTellSubsystem / UBlackjackTrustSubsystem) to the
 * data sources available in v1. Intended to be dropped into a level BP's
 * BeginPlay.
 */
UCLASS()
class BLACKJACKUE_API UBlackjackPerceptionWiring : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Drop this into your level BP's BeginPlay. It connects the
     *  TellSubsystem to the NetClient.OnGestureMade delegate and
     *  the TrustSubsystem to a pair of designer-driven bluff events. */
    UFUNCTION(BlueprintCallable, Category="Blackjack|Perception", meta=(WorldContext="WorldContextObject"))
    static void InstallPerceptionWiring(UObject* WorldContextObject);
};
