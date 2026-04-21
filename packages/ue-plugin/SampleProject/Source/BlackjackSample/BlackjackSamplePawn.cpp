#include "BlackjackSamplePawn.h"

#include "Camera/CameraComponent.h"

ABlackjackSamplePawn::ABlackjackSamplePawn()
{
    // Disable DefaultPawn movement — this pawn is a static camera host.
    GetMovementComponent()->SetComponentTickEnabled(false);
    bUseControllerRotationPitch = false;
    bUseControllerRotationYaw = false;
    bUseControllerRotationRoll = false;

    TableCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("TableCamera"));
    TableCamera->SetupAttachment(RootComponent);
    // Vantage: ~3 m up, 3 m back, pitched down 45 deg toward world origin.
    TableCamera->SetRelativeLocation(FVector(-300.f, 0.f, 300.f));
    TableCamera->SetRelativeRotation(FRotator(-45.f, 0.f, 0.f));
    TableCamera->FieldOfView = 75.f;
    TableCamera->bUsePawnControlRotation = false;
}
