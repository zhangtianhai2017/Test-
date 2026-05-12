#pragma once

#include "CoreMinimal.h"
#include "UObject/NoExportTypes.h"
#include "Interfaces/IHttpRequest.h"
#include "OutfitManifest.h"
#include "OutfitDownloader.generated.h"

DECLARE_DELEGATE_TwoParams(FOnManifestReady, bool /*bSuccess*/, const FOutfitManifest& /*Manifest*/);
DECLARE_DELEGATE_TwoParams(FOnGlbReady,      bool /*bSuccess*/, const TArray<uint8>& /*Bytes*/);

UCLASS()
class BIKINIVALIDATOR_API UOutfitDownloader : public UObject
{
	GENERATED_BODY()

public:
	void Configure(const FString& InBaseRawUrl, const FString& InCacheDir);

	void FetchManifest(FOnManifestReady OnReady);
	void FetchGlb(const FString& File, FOnGlbReady OnReady);

private:
	FString BaseRawUrl;
	FString CacheDir;

	void HandleManifestResponse(FHttpRequestPtr Req, FHttpResponsePtr Resp, bool bOk, FOnManifestReady OnReady);
	void HandleGlbResponse(FHttpRequestPtr Req, FHttpResponsePtr Resp, bool bOk, FString File, FOnGlbReady OnReady);

	bool TryReadCache(const FString& File, TArray<uint8>& OutBytes) const;
	void WriteCache(const FString& File, const TArray<uint8>& Bytes) const;
};
