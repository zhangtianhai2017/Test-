#pragma once

#include "CoreMinimal.h"
#include "UObject/NoExportTypes.h"
#include "OutfitLoader.generated.h"

class USkeleton;
class USkeletalMeshComponent;

UCLASS()
class BIKINIVALIDATOR_API UOutfitLoader : public UObject
{
	GENERATED_BODY()

public:
	void Configure(USkeleton* InMetaHumanSkeleton);

	// Loads a skinned glTF from raw bytes via glTFRuntime, binds the resulting
	// USkeletalMesh to the configured MetaHuman USkeleton, spawns a new actor,
	// and SetMasterPoseComponent's the spawned mesh component to the MetaHuman
	// body so the outfit deforms with character animation.
	AActor* SpawnSkinnedFromBytes(UWorld* World, const TArray<uint8>& Bytes,
	                              USkeletalMeshComponent* MetaHumanBodyComp);

private:
	UPROPERTY() USkeleton* MetaHumanSkeleton = nullptr;
};
