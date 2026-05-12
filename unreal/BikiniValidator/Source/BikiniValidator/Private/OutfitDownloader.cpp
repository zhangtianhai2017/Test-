#include "OutfitDownloader.h"
#include "HttpModule.h"
#include "Interfaces/IHttpResponse.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/PlatformFileManager.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

void UOutfitDownloader::Configure(const FString& InBaseRawUrl, const FString& InCacheDir)
{
	BaseRawUrl = InBaseRawUrl;
	if (!BaseRawUrl.EndsWith(TEXT("/"))) { BaseRawUrl += TEXT("/"); }
	CacheDir = InCacheDir;
	IPlatformFile& PF = FPlatformFileManager::Get().GetPlatformFile();
	if (!PF.DirectoryExists(*CacheDir)) { PF.CreateDirectoryTree(*CacheDir); }
}

void UOutfitDownloader::FetchManifest(FOnManifestReady OnReady)
{
	const FString Url = BaseRawUrl + TEXT("manifest.json");
	auto Req = FHttpModule::Get().CreateRequest();
	Req->SetVerb(TEXT("GET"));
	Req->SetURL(Url);
	Req->OnProcessRequestComplete().BindUObject(this, &UOutfitDownloader::HandleManifestResponse, OnReady);
	Req->ProcessRequest();
}

void UOutfitDownloader::HandleManifestResponse(FHttpRequestPtr Req, FHttpResponsePtr Resp, bool bOk, FOnManifestReady OnReady)
{
	FOutfitManifest M;
	if (!bOk || !Resp.IsValid() || Resp->GetResponseCode() != 200)
	{
		UE_LOG(LogTemp, Error, TEXT("[OutfitDownloader] manifest HTTP failed (code=%d)"), Resp.IsValid() ? Resp->GetResponseCode() : -1);
		OnReady.ExecuteIfBound(false, M);
		return;
	}

	const FString Body = Resp->GetContentAsString();
	TSharedPtr<FJsonObject> Root;
	auto Reader = TJsonReaderFactory<>::Create(Body);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
	{
		UE_LOG(LogTemp, Error, TEXT("[OutfitDownloader] manifest JSON parse failed"));
		OnReady.ExecuteIfBound(false, M);
		return;
	}

	M.Version  = Root->GetIntegerField(TEXT("version"));
	M.Branch   = Root->GetStringField(TEXT("branch"));
	M.Skeleton = Root->GetStringField(TEXT("skeleton"));

	const TArray<TSharedPtr<FJsonValue>>* OutfitsArr = nullptr;
	if (Root->TryGetArrayField(TEXT("outfits"), OutfitsArr) && OutfitsArr)
	{
		for (const TSharedPtr<FJsonValue>& V : *OutfitsArr)
		{
			const TSharedPtr<FJsonObject> O = V->AsObject();
			if (!O.IsValid()) { continue; }
			FOutfitEntry E;
			E.Seed       = O->GetStringField(TEXT("seed"));
			E.File       = O->GetStringField(TEXT("file"));
			E.Archetype  = O->GetStringField(TEXT("archetype"));
			O->TryGetNumberField(TEXT("kb"), E.Kb);
			O->TryGetNumberField(TEXT("vertex_count"), E.VertexCount);

			const TArray<TSharedPtr<FJsonValue>>* SlotsArr = nullptr;
			if (O->TryGetArrayField(TEXT("slots"), SlotsArr) && SlotsArr)
			{
				for (const TSharedPtr<FJsonValue>& SV : *SlotsArr)
				{
					const TSharedPtr<FJsonObject> SO = SV->AsObject();
					if (!SO.IsValid()) { continue; }
					FOutfitSlot S;
					S.Name      = SO->GetStringField(TEXT("name"));
					S.LibraryId = SO->GetStringField(TEXT("library_id"));
					E.Slots.Add(S);
				}
			}
			M.Outfits.Add(E);
		}
	}

	UE_LOG(LogTemp, Log, TEXT("[OutfitDownloader] manifest loaded: %d outfits"), M.Outfits.Num());
	OnReady.ExecuteIfBound(true, M);
}

void UOutfitDownloader::FetchGlb(const FString& File, FOnGlbReady OnReady)
{
	TArray<uint8> Cached;
	if (TryReadCache(File, Cached))
	{
		UE_LOG(LogTemp, Log, TEXT("[OutfitDownloader] cache hit %s (%d bytes)"), *File, Cached.Num());
		OnReady.ExecuteIfBound(true, Cached);
		return;
	}

	const FString Url = BaseRawUrl + File;
	auto Req = FHttpModule::Get().CreateRequest();
	Req->SetVerb(TEXT("GET"));
	Req->SetURL(Url);
	Req->OnProcessRequestComplete().BindUObject(this, &UOutfitDownloader::HandleGlbResponse, File, OnReady);
	Req->ProcessRequest();
}

void UOutfitDownloader::HandleGlbResponse(FHttpRequestPtr Req, FHttpResponsePtr Resp, bool bOk, FString File, FOnGlbReady OnReady)
{
	if (!bOk || !Resp.IsValid() || Resp->GetResponseCode() != 200)
	{
		UE_LOG(LogTemp, Error, TEXT("[OutfitDownloader] glb HTTP failed for %s (code=%d)"), *File, Resp.IsValid() ? Resp->GetResponseCode() : -1);
		OnReady.ExecuteIfBound(false, TArray<uint8>());
		return;
	}
	const TArray<uint8>& Bytes = Resp->GetContent();
	WriteCache(File, Bytes);
	UE_LOG(LogTemp, Log, TEXT("[OutfitDownloader] downloaded %s (%d bytes)"), *File, Bytes.Num());
	OnReady.ExecuteIfBound(true, Bytes);
}

bool UOutfitDownloader::TryReadCache(const FString& File, TArray<uint8>& OutBytes) const
{
	const FString Path = FPaths::Combine(CacheDir, File);
	return FFileHelper::LoadFileToArray(OutBytes, *Path);
}

void UOutfitDownloader::WriteCache(const FString& File, const TArray<uint8>& Bytes) const
{
	const FString Path = FPaths::Combine(CacheDir, File);
	FFileHelper::SaveArrayToFile(Bytes, *Path);
}
