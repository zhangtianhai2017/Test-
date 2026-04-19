#include "BlackjackTableActor.h"
#include "BlackjackGameComponent.h"
#include "BlackjackCardActor.h"
#include "BlackjackChipStackActor.h"
#include "BlackjackDealerCharacter.h"
#include "Components/StaticMeshComponent.h"
#include "UObject/ConstructorHelpers.h"

ABlackjackTableActor::ABlackjackTableActor()
{
    PrimaryActorTick.bCanEverTick = false;
    TableMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("TableMesh"));
    RootComponent = TableMesh;
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cyl(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    if (Cyl.Succeeded()) TableMesh->SetStaticMesh(Cyl.Object);
    TableMesh->SetRelativeScale3D(FVector(2.2f, 2.2f, 0.08f));

    GameComponent = CreateDefaultSubobject<UBlackjackGameComponent>(TEXT("GameComponent"));

    CardActorClass = ABlackjackCardActor::StaticClass();
    ChipStackClass = ABlackjackChipStackActor::StaticClass();
}

void ABlackjackTableActor::BeginPlay()
{
    Super::BeginPlay();
    if (!GameComponent) return;

    GameComponent->OnCardDealt.AddDynamic(this, &ABlackjackTableActor::HandleCardDealt);
    GameComponent->OnHoleCardRevealed.AddDynamic(this, &ABlackjackTableActor::HandleHoleCardRevealed);
    GameComponent->OnRoundOver.AddDynamic(this, &ABlackjackTableActor::HandleRoundOver);
    GameComponent->OnPhaseChanged.AddDynamic(this, &ABlackjackTableActor::HandlePhaseChanged);
    GameComponent->OnBankrollChanged.AddDynamic(this, &ABlackjackTableActor::HandleBankrollChanged);

    if (UWorld* World = GetWorld(); World && ChipStackClass)
    {
        FActorSpawnParameters Sp;
        Sp.Owner = this;
        BankrollStack = World->SpawnActor<ABlackjackChipStackActor>(ChipStackClass, GetActorLocation() + FVector(60.f, 0.f, 5.f), FRotator::ZeroRotator, Sp);
        if (BankrollStack) BankrollStack->SetChipCount(GameComponent->GetBankroll() / 25);
    }
}

FVector ABlackjackTableActor::CardTargetFor(EBlackjackTarget To, int32 HandIndex, int32 CardIndex) const
{
    const FVector Base = GetActorLocation() + (To == EBlackjackTarget::Dealer ? DealerSlotOffset : PlayerSlotOffset);
    const float HandOffsetY = (To == EBlackjackTarget::Player) ? HandIndex * 25.f : 0.f;
    return Base + FVector(CardIndex * CardSpreadX, HandOffsetY, 0.f);
}

void ABlackjackTableActor::HandleCardDealt(EBlackjackTarget To, int32 HandIndex, FBlackjackCard Card, bool bFaceDown)
{
    if (!CardActorClass || !GetWorld()) return;
    FActorSpawnParameters Sp;
    Sp.Owner = this;
    ABlackjackCardActor* CardActor = GetWorld()->SpawnActor<ABlackjackCardActor>(
        CardActorClass, GetActorLocation() + DeckSpawnOffset, FRotator::ZeroRotator, Sp);
    if (!CardActor) return;
    CardActor->InitializeCard(Card, bFaceDown);

    int32 CardIndex;
    if (To == EBlackjackTarget::Dealer)
    {
        CardIndex = DealerCardIndex++;
        if (bFaceDown) HoleCardActor = CardActor;
    }
    else
    {
        CardIndex = 0;
        for (const ABlackjackCardActor* C : SpawnedCards)
        {
            if (C && C != CardActor) ++CardIndex;
        }
    }
    const FVector Target = CardTargetFor(To, HandIndex, CardIndex);
    const FRotator TargetRot = bFaceDown ? FRotator(180.f, 0.f, 0.f) : FRotator::ZeroRotator;
    CardActor->PlayDealAnimation(GetActorLocation() + DeckSpawnOffset, Target, TargetRot);
    SpawnedCards.Add(CardActor);

    if (Dealer) Dealer->PlayDeal();
}

void ABlackjackTableActor::HandleHoleCardRevealed(FBlackjackCard /*Card*/)
{
    if (HoleCardActor) HoleCardActor->FlipFaceUp();
    if (Dealer) Dealer->PlayFlipHole();
}

void ABlackjackTableActor::HandleRoundOver(const TArray<FBlackjackHandResult>& Results)
{
    if (Dealer)
    {
        bool bAnyWin = false;
        for (const FBlackjackHandResult& R : Results)
        {
            if (R.Outcome == EBlackjackOutcome::Win || R.Outcome == EBlackjackOutcome::Blackjack) { bAnyWin = true; break; }
        }
        if (bAnyWin) Dealer->PlayPay();
        else Dealer->PlayCollect();
    }
}

void ABlackjackTableActor::HandlePhaseChanged(EBlackjackPhase NewPhase)
{
    if (NewPhase == EBlackjackPhase::Betting) ClearSpawnedCards();
}

void ABlackjackTableActor::HandleBankrollChanged(int32 NewBankroll, int32 /*Delta*/)
{
    if (BankrollStack) BankrollStack->SetChipCount(NewBankroll / 25);
}

void ABlackjackTableActor::ClearSpawnedCards()
{
    for (ABlackjackCardActor* C : SpawnedCards) if (C) C->Destroy();
    SpawnedCards.Reset();
    DealerCardIndex = 0;
    HoleCardActor = nullptr;
}
