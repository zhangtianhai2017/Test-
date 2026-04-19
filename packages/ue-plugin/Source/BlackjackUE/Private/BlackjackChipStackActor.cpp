#include "BlackjackChipStackActor.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "UObject/ConstructorHelpers.h"

ABlackjackChipStackActor::ABlackjackChipStackActor()
{
    ChipInstances = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("ChipInstances"));
    RootComponent = ChipInstances;
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cyl(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    if (Cyl.Succeeded()) ChipInstances->SetStaticMesh(Cyl.Object);
    ChipInstances->SetRelativeScale3D(FVector(0.1f, 0.1f, 0.02f));
}

void ABlackjackChipStackActor::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);
    RebuildInstances();
}

void ABlackjackChipStackActor::SetChipCount(int32 NewCount)
{
    ChipCount = FMath::Max(0, NewCount);
    RebuildInstances();
}

void ABlackjackChipStackActor::RebuildInstances()
{
    if (!ChipInstances) return;
    ChipInstances->ClearInstances();
    const int32 Visible = FMath::Min(ChipCount, 40);
    for (int32 I = 0; I < Visible; ++I)
    {
        FTransform T;
        T.SetLocation(FVector(0.f, 0.f, 4.f * I));
        ChipInstances->AddInstance(T);
    }
}
