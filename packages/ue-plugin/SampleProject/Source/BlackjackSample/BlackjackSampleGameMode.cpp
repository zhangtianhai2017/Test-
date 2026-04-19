#include "BlackjackSampleGameMode.h"
#include "BlackjackTableActor.h"
#include "BlackjackGameComponent.h"
#include "BlackjackDealerCharacter.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"

ABlackjackSampleGameMode::ABlackjackSampleGameMode()
{
    PrimaryActorTick.bCanEverTick = false;
}

void ABlackjackSampleGameMode::BeginPlay()
{
    Super::BeginPlay();
    UWorld* World = GetWorld();
    if (!World) return;

    FActorSpawnParameters Sp;
    ABlackjackTableActor* Table = World->SpawnActor<ABlackjackTableActor>(
        ABlackjackTableActor::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, Sp);

    ABlackjackDealerCharacter* DealerChar = World->SpawnActor<ABlackjackDealerCharacter>(
        ABlackjackDealerCharacter::StaticClass(), FVector(0.f, -120.f, 0.f), FRotator(0.f, 90.f, 0.f), Sp);
    if (Table) Table->Dealer = DealerChar;
}
