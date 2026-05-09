#include "OutfitLoader.h"
#include "Engine/World.h"
#include "Engine/SkeletalMesh.h"
#include "Animation/Skeleton.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/Actor.h"
#include "glTFRuntimeFunctionLibrary.h"
#include "glTFRuntimeAsset.h"

void UOutfitLoader::Configure(USkeleton* InMetaHumanSkeleton)
{
	MetaHumanSkeleton = InMetaHumanSkeleton;
}

AActor* UOutfitLoader::SpawnSkinnedFromBytes(UWorld* World, const TArray<uint8>& Bytes,
                                             USkeletalMeshComponent* MetaHumanBodyComp)
{
	if (!World || Bytes.Num() == 0 || !MetaHumanSkeleton)
	{
		UE_LOG(LogTemp, Error, TEXT("[OutfitLoader] Spawn precondition failed (world=%d bytes=%d skel=%d)"),
		       World != nullptr, Bytes.Num(), MetaHumanSkeleton != nullptr);
		return nullptr;
	}

	FglTFRuntimeConfig RuntimeConfig;
	RuntimeConfig.TransformBaseType = EglTFRuntimeTransformBaseType::YForward;
	UglTFRuntimeAsset* Asset = UglTFRuntimeFunctionLibrary::glTFLoadAssetFromData(Bytes, RuntimeConfig);
	if (!Asset)
	{
		UE_LOG(LogTemp, Error, TEXT("[OutfitLoader] glTFLoadAssetFromData failed"));
		return nullptr;
	}

	FglTFRuntimeSkeletalMeshConfig MeshConfig;
	MeshConfig.SkeletonConfig.bAddRootBone = false;
	MeshConfig.Skeleton = MetaHumanSkeleton;          // share existing skeleton
	MeshConfig.SkeletonConfig.CopyRotationsFrom = MetaHumanSkeleton;

	USkeletalMesh* Mesh = Asset->LoadSkeletalMesh(0, 0, MeshConfig);
	if (!Mesh)
	{
		UE_LOG(LogTemp, Error, TEXT("[OutfitLoader] LoadSkeletalMesh returned null"));
		return nullptr;
	}

	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AActor* OutfitActor = World->SpawnActor<AActor>(AActor::StaticClass(), FTransform::Identity, SpawnParams);
	if (!OutfitActor) { return nullptr; }

	USkeletalMeshComponent* SkelComp = NewObject<USkeletalMeshComponent>(OutfitActor);
	SkelComp->SetSkeletalMeshAsset(Mesh);
	SkelComp->SetupAttachment(OutfitActor->GetRootComponent() ? OutfitActor->GetRootComponent() : nullptr);
	OutfitActor->SetRootComponent(SkelComp);
	SkelComp->RegisterComponent();

	if (MetaHumanBodyComp)
	{
		// Follow the MetaHuman's animation pose every tick.
		SkelComp->SetMasterPoseComponent(MetaHumanBodyComp);
		OutfitActor->AttachToComponent(MetaHumanBodyComp,
			FAttachmentTransformRules::SnapToTargetIncludingScale);
	}

	return OutfitActor;
}
