#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "OutfitManifest.h"
#include "BikiniValidatorGameMode.generated.h"

class UOutfitDownloader;
class UOutfitLoader;
class USimpleSelectorWidget;
class AOrbitPawn;
class ACharacter;
class USkeletalMeshComponent;
class USkeleton;

UCLASS()
class BIKINIVALIDATOR_API ABikiniValidatorGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	ABikiniValidatorGameMode();

	// Soft refs configurable in DefaultEngine.ini or set in C++ ctor.
	UPROPERTY(EditDefaultsOnly, Category="MetaHuman")
	FSoftObjectPath MetaHumanBPPath;

	UPROPERTY(EditDefaultsOnly, Category="MetaHuman")
	FSoftObjectPath MetaHumanSkeletonPath;

	UPROPERTY(EditDefaultsOnly, Category="Network")
	FString BaseRawUrl;

protected:
	virtual void BeginPlay() override;

	void SpawnLighting();
	void SpawnMetaHuman();
	void SpawnOrbitPawn();
	void BuildUI();
	void StartManifestFetch();

	UFUNCTION() void HandleManifestReady(bool bSuccess, const FOutfitManifest& M);
	UFUNCTION() void HandleLoadClicked(FString File);
	UFUNCTION() void HandleGlbReady(bool bSuccess, const TArray<uint8>& Bytes);

	UPROPERTY() ACharacter*               MetaHumanActor   = nullptr;
	UPROPERTY() USkeletalMeshComponent*   MetaHumanBodyComp = nullptr;
	UPROPERTY() USkeleton*                MetaHumanSkeleton = nullptr;
	UPROPERTY() AActor*                   CurrentOutfitActor = nullptr;
	UPROPERTY() AOrbitPawn*               OrbitPawn        = nullptr;
	UPROPERTY() UOutfitDownloader*        Downloader       = nullptr;
	UPROPERTY() UOutfitLoader*            Loader           = nullptr;
	UPROPERTY() USimpleSelectorWidget*    Widget           = nullptr;
};
