#include "BikiniValidatorGameMode.h"
#include "OutfitDownloader.h"
#include "OutfitLoader.h"
#include "SimpleSelectorWidget.h"
#include "OrbitPawn.h"

#include "Engine/World.h"
#include "Engine/SkyLight.h"
#include "Engine/DirectionalLight.h"
#include "Components/SkyLightComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "Animation/Skeleton.h"
#include "Misc/Paths.h"
#include "UObject/ConstructorHelpers.h"
#include "Kismet/GameplayStatics.h"
#include "Blueprint/UserWidget.h"

ABikiniValidatorGameMode::ABikiniValidatorGameMode()
{
	BaseRawUrl = TEXT("https://raw.githubusercontent.com/zhangtianhai2017/Test-/claude/bikini-variation-algorithm-Dv5q5/assets/glb/");

	MetaHumanBPPath = FSoftObjectPath(TEXT("/Game/MetaHumans/NPC_swim_G_34/BP_NPC_swim_G_34.BP_NPC_swim_G_34_C"));
	// MetaHumanSkeletonPath left empty — resolved automatically from the
	// spawned body mesh in SpawnMetaHuman().

	DefaultPawnClass = AOrbitPawn::StaticClass();
}

void ABikiniValidatorGameMode::BeginPlay()
{
	Super::BeginPlay();

	SpawnLighting();
	SpawnMetaHuman();
	SpawnOrbitPawn();
	BuildUI();
	StartManifestFetch();
}

void ABikiniValidatorGameMode::SpawnLighting()
{
	UWorld* W = GetWorld();
	if (!W) { return; }

	ADirectionalLight* Sun = W->SpawnActor<ADirectionalLight>(ADirectionalLight::StaticClass(),
		FVector::ZeroVector, FRotator(-45.f, -30.f, 0.f));
	if (Sun && Sun->GetLightComponent())
	{
		Sun->GetLightComponent()->SetIntensity(5.f);
	}

	W->SpawnActor<ASkyLight>(ASkyLight::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator);
}

void ABikiniValidatorGameMode::SpawnMetaHuman()
{
	UWorld* W = GetWorld();
	if (!W) { return; }

	if (!MetaHumanBPPath.IsValid())
	{
		UE_LOG(LogTemp, Error, TEXT("[GameMode] MetaHumanBPPath is empty — set it on the GameMode default object after dropping the MetaHuman .uasset into Content/MetaHuman/."));
		return;
	}

	UClass* Cls = LoadObject<UClass>(nullptr, *MetaHumanBPPath.ToString());
	if (!Cls)
	{
		UE_LOG(LogTemp, Error, TEXT("[GameMode] Failed to load MetaHuman BP: %s"), *MetaHumanBPPath.ToString());
		return;
	}

	MetaHumanActor = W->SpawnActor<ACharacter>(Cls, FVector::ZeroVector, FRotator::ZeroRotator);
	if (MetaHumanActor)
	{
		MetaHumanBodyComp = MetaHumanActor->GetMesh();
	}

	if (MetaHumanSkeletonPath.IsValid())
	{
		MetaHumanSkeleton = Cast<USkeleton>(MetaHumanSkeletonPath.TryLoad());
	}
	else if (MetaHumanBodyComp && MetaHumanBodyComp->GetSkeletalMeshAsset())
	{
		MetaHumanSkeleton = MetaHumanBodyComp->GetSkeletalMeshAsset()->GetSkeleton();
	}

	if (!MetaHumanSkeleton)
	{
		UE_LOG(LogTemp, Error, TEXT("[GameMode] Failed to resolve MetaHuman USkeleton — outfit skinning will fail."));
	}
}

void ABikiniValidatorGameMode::SpawnOrbitPawn()
{
	UWorld* W = GetWorld();
	if (!W) { return; }

	APlayerController* PC = UGameplayStatics::GetPlayerController(W, 0);
	if (!PC) { return; }

	OrbitPawn = W->SpawnActor<AOrbitPawn>(AOrbitPawn::StaticClass(),
		FVector(0.f, 0.f, 130.f), FRotator::ZeroRotator);
	if (OrbitPawn)
	{
		PC->Possess(OrbitPawn);
		FVector Pelvis = MetaHumanActor ? MetaHumanActor->GetActorLocation() + FVector(0.f, 0.f, 100.f) : FVector::ZeroVector;
		OrbitPawn->SetTarget(Pelvis);
	}
}

void ABikiniValidatorGameMode::BuildUI()
{
	UWorld* W = GetWorld();
	if (!W) { return; }
	APlayerController* PC = UGameplayStatics::GetPlayerController(W, 0);
	if (!PC) { return; }

	Widget = CreateWidget<USimpleSelectorWidget>(PC, USimpleSelectorWidget::StaticClass());
	if (Widget)
	{
		Widget->AddToViewport(10);
		Widget->OnLoadClicked.AddDynamic(this, &ABikiniValidatorGameMode::HandleLoadClicked);
	}
}

void ABikiniValidatorGameMode::StartManifestFetch()
{
	const FString CacheDir = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Cache/glb/"));

	Downloader = NewObject<UOutfitDownloader>(this);
	Downloader->Configure(BaseRawUrl, CacheDir);

	Loader = NewObject<UOutfitLoader>(this);
	Loader->Configure(MetaHumanSkeleton);

	FOnManifestReady CB;
	CB.BindUObject(this, &ABikiniValidatorGameMode::HandleManifestReady);
	Downloader->FetchManifest(CB);
}

void ABikiniValidatorGameMode::HandleManifestReady(bool bSuccess, const FOutfitManifest& M)
{
	if (!bSuccess)
	{
		UE_LOG(LogTemp, Error, TEXT("[GameMode] manifest fetch failed"));
		return;
	}
	if (Widget)
	{
		Widget->Populate(M);
	}
}

void ABikiniValidatorGameMode::HandleLoadClicked(FString File)
{
	if (!Downloader) { return; }
	UE_LOG(LogTemp, Log, TEXT("[GameMode] load clicked: %s"), *File);

	FOnGlbReady CB;
	CB.BindUObject(this, &ABikiniValidatorGameMode::HandleGlbReady);
	Downloader->FetchGlb(File, CB);
}

void ABikiniValidatorGameMode::HandleGlbReady(bool bSuccess, const TArray<uint8>& Bytes)
{
	if (!bSuccess || !Loader) { return; }

	if (CurrentOutfitActor)
	{
		CurrentOutfitActor->Destroy();
		CurrentOutfitActor = nullptr;
	}

	CurrentOutfitActor = Loader->SpawnSkinnedFromBytes(GetWorld(), Bytes, MetaHumanBodyComp);
	if (!CurrentOutfitActor)
	{
		UE_LOG(LogTemp, Error, TEXT("[GameMode] outfit spawn failed"));
	}
}
