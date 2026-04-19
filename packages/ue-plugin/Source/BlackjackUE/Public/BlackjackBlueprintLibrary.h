#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "BlackjackTypes.h"
#include "BlackjackBlueprintLibrary.generated.h"

UCLASS()
class BLACKJACKUE_API UBlackjackBlueprintLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintPure, Category = "Blackjack") static FString CardToString(const FBlackjackCard& Card);
    UFUNCTION(BlueprintPure, Category = "Blackjack") static int32 HandTotal(const TArray<FBlackjackCard>& Cards);
    UFUNCTION(BlueprintPure, Category = "Blackjack") static bool IsBlackjack(const TArray<FBlackjackCard>& Cards);
    UFUNCTION(BlueprintPure, Category = "Blackjack") static bool IsBust(const TArray<FBlackjackCard>& Cards);
    UFUNCTION(BlueprintPure, Category = "Blackjack") static FString OutcomeToString(EBlackjackOutcome Outcome);
    UFUNCTION(BlueprintPure, Category = "Blackjack") static FString PhaseToString(EBlackjackPhase Phase);
};
