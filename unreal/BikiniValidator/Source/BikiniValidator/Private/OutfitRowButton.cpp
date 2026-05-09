#include "OutfitRowButton.h"
#include "Components/Button.h"

void UOutfitRowButton::Bind(UButton* InButton, const FString& InFile)
{
	Button = InButton;
	File   = InFile;
	if (Button)
	{
		Button->OnClicked.AddDynamic(this, &UOutfitRowButton::HandleClicked);
	}
}

void UOutfitRowButton::HandleClicked()
{
	OnFileClicked.Broadcast(File);
}
