#include "BlackjackCardActor.h"
#include "Components/StaticMeshComponent.h"
#include "UObject/ConstructorHelpers.h"

ABlackjackCardActor::ABlackjackCardActor()
{
    PrimaryActorTick.bCanEverTick = true;
    CardMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CardMesh"));
    RootComponent = CardMesh;
    // Placeholder: a thin cube scaled to card proportions (6 x 0.1 x 8.5 UE units).
    // Designers override the mesh asset in a child Blueprint with their own card mesh.
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
    if (Cube.Succeeded()) CardMesh->SetStaticMesh(Cube.Object);
    CardMesh->SetRelativeScale3D(FVector(0.06f, 0.001f, 0.085f));
}

void ABlackjackCardActor::BeginPlay()
{
    Super::BeginPlay();
}

void ABlackjackCardActor::InitializeCard(const FBlackjackCard& InCard, bool bInFaceDown)
{
    Card = InCard;
    bFaceDown = bInFaceDown;
}

void ABlackjackCardActor::FlipFaceUp()
{
    bFaceDown = false;
    AddActorLocalRotation(FRotator(180.f, 0.f, 0.f));
}

void ABlackjackCardActor::PlayDealAnimation_Implementation(FVector FromLocation, FVector ToLocation, FRotator ToRotation)
{
    FromLoc = FromLocation;
    TargetLocation = ToLocation;
    TargetRotation = ToRotation;
    Elapsed = 0.f;
    bTweening = true;
    SetActorLocation(FromLocation);
    SetActorRotation(ToRotation);
}

void ABlackjackCardActor::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!bTweening) return;
    Elapsed += DeltaSeconds;
    const float T = FMath::Clamp(Elapsed / FMath::Max(0.01f, DealDuration), 0.f, 1.f);
    const float E = 1.f - FMath::Pow(1.f - T, 3.f);
    SetActorLocation(FMath::Lerp(FromLoc, TargetLocation, E));
    if (T >= 1.f) bTweening = false;
}
