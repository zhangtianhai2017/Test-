#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "OutfitManifest.h"
#include "SimpleSelectorWidget.generated.h"

class UScrollBox;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnLoadClicked, FString, File);

UCLASS()
class BIKINIVALIDATOR_API USimpleSelectorWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	USimpleSelectorWidget(const FObjectInitializer& OI);

	virtual TSharedRef<SWidget> RebuildWidget() override;

	void Populate(const FOutfitManifest& M);

	UPROPERTY(BlueprintAssignable) FOnLoadClicked OnLoadClicked;

private:
	UPROPERTY() UScrollBox* Scroll = nullptr;
	UPROPERTY() TArray<class UOutfitRowButton*> RowBindings;
	FOutfitManifest CachedManifest;

	UFUNCTION() void HandleRowClicked(FString File);
};
