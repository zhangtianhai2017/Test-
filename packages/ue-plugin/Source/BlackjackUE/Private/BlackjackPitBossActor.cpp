#include "BlackjackPitBossActor.h"

#include "BlackjackHeatSubsystem.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/GameInstance.h"

ABlackjackPitBossActor::ABlackjackPitBossActor()
{
    PrimaryActorTick.bCanEverTick = false;

    MeshComponent = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("PitBossMesh"));
    RootComponent = MeshComponent;
}

void ABlackjackPitBossActor::BeginPlay()
{
    Super::BeginPlay();

    // Start hidden; SetPresent(true) will un-hide and flip collision back on.
    SetActorHiddenInGame(true);
    SetActorEnableCollision(false);
    bPresent = false;

    if (UGameInstance* GI = GetGameInstance())
    {
        if (UBlackjackHeatSubsystem* Heat = GI->GetSubsystem<UBlackjackHeatSubsystem>())
        {
            Heat->OnHeatChanged.AddDynamic(this, &ABlackjackPitBossActor::HandleHeatChanged);

            // Sync to current heat in case the boss is placed mid-round at an
            // already-elevated heat level.
            HandleHeatChanged(Heat->GetHeat(), 0);
        }
    }
}

void ABlackjackPitBossActor::EndPlay(const EEndPlayReason::Type Reason)
{
    if (UGameInstance* GI = GetGameInstance())
    {
        if (UBlackjackHeatSubsystem* Heat = GI->GetSubsystem<UBlackjackHeatSubsystem>())
        {
            Heat->OnHeatChanged.RemoveDynamic(this, &ABlackjackPitBossActor::HandleHeatChanged);
        }
    }

    Super::EndPlay(Reason);
}

void ABlackjackPitBossActor::HandleHeatChanged(int32 NewHeat, int32 /*Delta*/)
{
    if (NewHeat >= ArriveAtHeat && !bPresent)
    {
        SetPresent(true);
    }
    else if (NewHeat <= DepartAtHeat && bPresent)
    {
        SetPresent(false);
    }
}

void ABlackjackPitBossActor::SetPresent(bool bNew)
{
    if (bPresent == bNew)
    {
        return;
    }
    bPresent = bNew;

    SetActorHiddenInGame(!bPresent);
    SetActorEnableCollision(bPresent);

    // Montage playback slot is intentionally left for designers to wire up in
    // Blueprint via the OnArrived / OnDeparted hooks below.
    if (bPresent)
    {
        OnArrived.Broadcast();
    }
    else
    {
        OnDeparted.Broadcast();
    }
}
