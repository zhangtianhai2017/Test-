#include "SimpleSelectorWidget.h"
#include "OutfitRowButton.h"
#include "Components/ScrollBox.h"
#include "Components/Button.h"
#include "Components/TextBlock.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Blueprint/WidgetTree.h"

USimpleSelectorWidget::USimpleSelectorWidget(const FObjectInitializer& OI)
	: Super(OI)
{
}

TSharedRef<SWidget> USimpleSelectorWidget::RebuildWidget()
{
	if (!WidgetTree->RootWidget)
	{
		UCanvasPanel* Root = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("Root"));
		WidgetTree->RootWidget = Root;

		Scroll = WidgetTree->ConstructWidget<UScrollBox>(UScrollBox::StaticClass(), TEXT("OutfitScroll"));
		UCanvasPanelSlot* CSlot = Cast<UCanvasPanelSlot>(Root->AddChild(Scroll));
		if (CSlot)
		{
			CSlot->SetAnchors(FAnchors(0.f, 0.f, 0.f, 1.f));
			CSlot->SetOffsets(FMargin(20.f, 20.f, 320.f, 20.f));
		}
	}
	return Super::RebuildWidget();
}

void USimpleSelectorWidget::Populate(const FOutfitManifest& M)
{
	CachedManifest = M;
	if (!Scroll) { return; }
	Scroll->ClearChildren();
	RowBindings.Reset();

	for (const FOutfitEntry& E : M.Outfits)
	{
		UButton* Btn = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass());
		UTextBlock* Label = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
		Label->SetText(FText::FromString(FString::Printf(TEXT("%s  (%s, %dKB)"), *E.Seed, *E.Archetype, E.Kb)));
		Btn->AddChild(Label);
		Scroll->AddChild(Btn);

		UOutfitRowButton* Binding = NewObject<UOutfitRowButton>(this);
		Binding->Bind(Btn, E.File);
		Binding->OnFileClicked.AddDynamic(this, &USimpleSelectorWidget::HandleRowClicked);
		RowBindings.Add(Binding);
	}
}

void USimpleSelectorWidget::HandleRowClicked(FString File)
{
	OnLoadClicked.Broadcast(File);
}
