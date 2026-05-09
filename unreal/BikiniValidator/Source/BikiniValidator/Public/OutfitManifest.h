#pragma once

#include "CoreMinimal.h"
#include "OutfitManifest.generated.h"

USTRUCT(BlueprintType)
struct FOutfitSlot
{
	GENERATED_BODY()

	UPROPERTY() FString Name;
	UPROPERTY() FString LibraryId;
};

USTRUCT(BlueprintType)
struct FOutfitEntry
{
	GENERATED_BODY()

	UPROPERTY() FString Seed;
	UPROPERTY() FString File;
	UPROPERTY() FString Archetype;
	UPROPERTY() TArray<FOutfitSlot> Slots;
	UPROPERTY() int32 Kb = 0;
	UPROPERTY() int32 VertexCount = 0;
};

USTRUCT(BlueprintType)
struct FOutfitManifest
{
	GENERATED_BODY()

	UPROPERTY() int32 Version = 0;
	UPROPERTY() FString Branch;
	UPROPERTY() FString Skeleton;
	UPROPERTY() TArray<FOutfitEntry> Outfits;
};
