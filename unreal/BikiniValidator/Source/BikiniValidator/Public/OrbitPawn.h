#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "OrbitPawn.generated.h"

class UCameraComponent;
class USpringArmComponent;

UCLASS()
class BIKINIVALIDATOR_API AOrbitPawn : public APawn
{
	GENERATED_BODY()

public:
	AOrbitPawn();

	void SetTarget(const FVector& WorldCenter);

	virtual void Tick(float DeltaTime) override;
	virtual void SetupPlayerInputComponent(UInputComponent* InputComp) override;

protected:
	virtual void BeginPlay() override;

	void HandleMouseX(float Value);
	void HandleMouseY(float Value);
	void HandleZoom(float Value);
	void HandleDragPressed();
	void HandleDragReleased();

	UPROPERTY(VisibleAnywhere) USceneComponent*      Pivot       = nullptr;
	UPROPERTY(VisibleAnywhere) USpringArmComponent*  SpringArm   = nullptr;
	UPROPERTY(VisibleAnywhere) UCameraComponent*     Camera      = nullptr;

	float Yaw    = 0.f;
	float Pitch  = -10.f;
	float Boom   = 220.f;
	bool  bDragging = false;
};
