#pragma once

#include "CoreMinimal.h"
#include "UObject/NoExportTypes.h"
#include "OutfitRowButton.generated.h"

class UButton;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnRowFileClicked, FString, File);

UCLASS()
class BIKINIVALIDATOR_API UOutfitRowButton : public UObject
{
	GENERATED_BODY()

public:
	void Bind(UButton* InButton, const FString& InFile);

	UPROPERTY() FOnRowFileClicked OnFileClicked;

private:
	UPROPERTY() UButton* Button = nullptr;
	UPROPERTY() FString File;

	UFUNCTION() void HandleClicked();
};
