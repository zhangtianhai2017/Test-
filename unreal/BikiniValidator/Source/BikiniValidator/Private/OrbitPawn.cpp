#include "OrbitPawn.h"
#include "Camera/CameraComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Components/InputComponent.h"
#include "GameFramework/PlayerController.h"

AOrbitPawn::AOrbitPawn()
{
	PrimaryActorTick.bCanEverTick = true;

	Pivot = CreateDefaultSubobject<USceneComponent>(TEXT("Pivot"));
	SetRootComponent(Pivot);

	SpringArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("SpringArm"));
	SpringArm->SetupAttachment(Pivot);
	SpringArm->bUsePawnControlRotation = false;
	SpringArm->bDoCollisionTest        = false;
	SpringArm->TargetArmLength         = Boom;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(SpringArm, USpringArmComponent::SocketName);
	Camera->SetFieldOfView(50.f);

	AutoPossessPlayer = EAutoReceiveInput::Player0;
}

void AOrbitPawn::SetTarget(const FVector& WorldCenter)
{
	SetActorLocation(WorldCenter);
}

void AOrbitPawn::BeginPlay()
{
	Super::BeginPlay();
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		PC->bShowMouseCursor = true;
		PC->SetInputMode(FInputModeGameAndUI());
	}
}

void AOrbitPawn::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	const FRotator R(Pitch, Yaw, 0.f);
	Pivot->SetWorldRotation(R);
	SpringArm->TargetArmLength = Boom;
}

void AOrbitPawn::SetupPlayerInputComponent(UInputComponent* InputComp)
{
	Super::SetupPlayerInputComponent(InputComp);
	InputComp->BindAxis(TEXT("MouseX"), this, &AOrbitPawn::HandleMouseX);
	InputComp->BindAxis(TEXT("MouseY"), this, &AOrbitPawn::HandleMouseY);
	InputComp->BindAxis(TEXT("Zoom"),   this, &AOrbitPawn::HandleZoom);
	InputComp->BindAction(TEXT("Drag"), IE_Pressed,  this, &AOrbitPawn::HandleDragPressed);
	InputComp->BindAction(TEXT("Drag"), IE_Released, this, &AOrbitPawn::HandleDragReleased);
}

void AOrbitPawn::HandleMouseX(float V)  { if (bDragging) { Yaw   += V * 2.f; } }
void AOrbitPawn::HandleMouseY(float V)  { if (bDragging) { Pitch  = FMath::Clamp(Pitch + V * 2.f, -85.f, 85.f); } }
void AOrbitPawn::HandleZoom(float V)    { Boom = FMath::Clamp(Boom - V * 20.f, 50.f, 800.f); }
void AOrbitPawn::HandleDragPressed()    { bDragging = true; }
void AOrbitPawn::HandleDragReleased()   { bDragging = false; }
