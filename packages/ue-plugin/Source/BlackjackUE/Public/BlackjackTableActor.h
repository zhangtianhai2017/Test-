#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "BlackjackTypes.h"
#include "BlackjackTableActor.generated.h"

class UBlackjackGameComponent;
class UStaticMeshComponent;
class ABlackjackCardActor;
class ABlackjackDealerCharacter;
class ABlackjackChipStackActor;

/**
 * Scene-facing Actor that owns a UBlackjackGameComponent and translates engine events
 * into real 3D actors: spawns ABlackjackCardActor instances on CARD_DEALT, triggers
 * dealer AnimMontages, updates chip stacks on BET_SETTLED, etc.
 *
 * Designers override BP_BlackjackTable in their project, assigning a dealer character,
 * card actor class, and chip-stack class. Storyline integration hooks (OnBigWin,
 * OnNaturalBlackjack, OnBankrupt) are surfaced as BP events on the GameComponent.
 */
UCLASS(Blueprintable)
class BLACKJACKUE_API ABlackjackTableActor : public AActor
{
    GENERATED_BODY()

public:
    ABlackjackTableActor();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly) UStaticMeshComponent* TableMesh;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly) UBlackjackGameComponent* GameComponent;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack") TSubclassOf<ABlackjackCardActor> CardActorClass;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack") TSubclassOf<ABlackjackChipStackActor> ChipStackClass;

    /** Assign in editor — the dealer character that plays deal/flip/pay montages. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack") ABlackjackDealerCharacter* Dealer;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Layout") FVector DeckSpawnOffset = FVector(-40.f, -40.f, 5.f);
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Layout") FVector DealerSlotOffset = FVector(0.f, -30.f, 5.f);
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Layout") FVector PlayerSlotOffset = FVector(0.f, 30.f, 5.f);
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Blackjack|Layout") float CardSpreadX = 8.f;

protected:
    virtual void BeginPlay() override;

    UFUNCTION() void HandleCardDealt(EBlackjackTarget To, int32 HandIndex, FBlackjackCard Card, bool bFaceDown);
    UFUNCTION() void HandleHoleCardRevealed(FBlackjackCard Card);
    UFUNCTION() void HandleRoundOver(const TArray<FBlackjackHandResult>& Results);
    UFUNCTION() void HandlePhaseChanged(EBlackjackPhase NewPhase);
    UFUNCTION() void HandleBankrollChanged(int32 NewBankroll, int32 Delta);

private:
    TArray<ABlackjackCardActor*> SpawnedCards;
    ABlackjackChipStackActor* BankrollStack = nullptr;
    int32 DealerCardIndex = 0;
    ABlackjackCardActor* HoleCardActor = nullptr;
    void ClearSpawnedCards();
    FVector CardTargetFor(EBlackjackTarget To, int32 HandIndex, int32 CardIndex) const;
};
