#include "BlackjackSampleGameMode.h"

#include "BlackjackSampleHUD.h"
#include "BlackjackSamplePawn.h"
#include "BlackjackSamplePlayerController.h"

#include "BlackjackCardActor.h"
#include "BlackjackChipStackActor.h"
#include "BlackjackDealerCharacter.h"
#include "BlackjackDecisionTimerActor.h"
#include "BlackjackNetClient.h"
#include "BlackjackNetTableActor.h"
#include "BlackjackPitBossActor.h"

#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "GameFramework/GameUserSettings.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

ABlackjackSampleGameMode::ABlackjackSampleGameMode()
{
    PrimaryActorTick.bCanEverTick = false;

    // Wire the pure-C++ classes so no BP GameMode is needed.
    DefaultPawnClass       = ABlackjackSamplePawn::StaticClass();
    PlayerControllerClass  = ABlackjackSamplePlayerController::StaticClass();
    HUDClass               = ABlackjackSampleHUD::StaticClass();
}

void ABlackjackSampleGameMode::BuildSeatLayout(TArray<FTransform>& OutSeats, FTransform& OutDealer)
{
    // Hex layout: 6 seats evenly around the table at radius 180 cm, facing origin.
    // Bet transforms are a bit closer so cards land on the felt just in front of each seat.
    OutSeats.Reset();
    const float BetRadius = 110.f;
    for (int32 i = 0; i < 6; ++i)
    {
        const float Angle = FMath::DegreesToRadians(60.f * i - 90.f); // seat 0 faces dealer
        const FVector Loc(FMath::Cos(Angle) * BetRadius, FMath::Sin(Angle) * BetRadius, 2.f);
        const FRotator Rot(0.f, FMath::RadiansToDegrees(Angle) + 180.f, 0.f);
        OutSeats.Add(FTransform(Rot, Loc));
    }
    // Dealer card spot: behind the felt, directly opposite seat 0.
    OutDealer = FTransform(FRotator::ZeroRotator, FVector(0.f, 90.f, 2.f));
}

void ABlackjackSampleGameMode::ParseConnectArgs(FString& OutHost, int32& OutPort, FString& OutName)
{
    OutHost = TEXT("127.0.0.1");
    OutPort = 7878;

    // Default name from GameUserSettings would be ideal, but 5.6 has no built-in
    // display-name field there, so we fall back to "TestPlayer" or -bjname=.
    OutName = TEXT("TestPlayer");

    const TCHAR* Cmd = FCommandLine::Get();
    FString Host;
    if (FParse::Value(Cmd, TEXT("-bjhost="), Host) && !Host.IsEmpty())
    {
        OutHost = Host;
    }
    int32 Port = 0;
    if (FParse::Value(Cmd, TEXT("-bjport="), Port) && Port > 0)
    {
        OutPort = Port;
    }
    FString Name;
    if (FParse::Value(Cmd, TEXT("-bjname="), Name) && !Name.IsEmpty())
    {
        OutName = Name;
    }
}

void ABlackjackSampleGameMode::BeginPlay()
{
    Super::BeginPlay();

    UWorld* World = GetWorld();
    if (!World) return;

    FActorSpawnParameters Sp;
    Sp.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

    // --- Net table at world origin ------------------------------------------
    NetTable = World->SpawnActor<ABlackjackNetTableActor>(
        ABlackjackNetTableActor::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, Sp);

    // --- Dealer character behind the table ----------------------------------
    DealerChar = World->SpawnActor<ABlackjackDealerCharacter>(
        ABlackjackDealerCharacter::StaticClass(), FVector(0.f, 120.f, 0.f),
        FRotator(0.f, -90.f, 0.f), Sp);

    // --- Pit boss off to the side -------------------------------------------
    PitBoss = World->SpawnActor<ABlackjackPitBossActor>(
        ABlackjackPitBossActor::StaticClass(), FVector(300.f, 120.f, 0.f),
        FRotator(0.f, -135.f, 0.f), Sp);

    // --- Decision timer (invisible — it's just a ticker) --------------------
    DecisionTimer = World->SpawnActor<ABlackjackDecisionTimerActor>(
        ABlackjackDecisionTimerActor::StaticClass(), FVector(0.f, 0.f, 100.f),
        FRotator::ZeroRotator, Sp);

    // --- Seat bet transforms + dealer transform -----------------------------
    TArray<FTransform> SeatBetTransforms;
    FTransform DealerBetTransform;
    BuildSeatLayout(SeatBetTransforms, DealerBetTransform);

    // --- 6 chip stack actors, one per seat ----------------------------------
    SeatChipStacks.Reset();
    for (int32 i = 0; i < SeatBetTransforms.Num(); ++i)
    {
        const FTransform& SeatXf = SeatBetTransforms[i];
        // Place each bankroll stack just outboard of the bet spot.
        FVector StackLoc = SeatXf.GetLocation() + SeatXf.GetRotation().Vector() * -30.f;
        StackLoc.Z = 0.f;
        ABlackjackChipStackActor* Stack = World->SpawnActor<ABlackjackChipStackActor>(
            ABlackjackChipStackActor::StaticClass(), StackLoc, FRotator::ZeroRotator, Sp);
        if (Stack)
        {
            SeatChipStacks.Add(Stack);
        }
    }

    // --- Wire up the net-table actor ---------------------------------------
    if (NetTable)
    {
        NetTable->CardActorClass       = ABlackjackCardActor::StaticClass();
        NetTable->ChipStackClass       = ABlackjackChipStackActor::StaticClass();
        NetTable->DealerCharacter      = DealerChar;
        NetTable->SeatBankrollStacks   = SeatChipStacks;
        NetTable->SeatBetTransforms    = SeatBetTransforms;
        NetTable->DealerBetTransform   = DealerBetTransform;
    }

    // --- Net client connection ---------------------------------------------
    FString Host, DisplayName; int32 Port;
    ParseConnectArgs(Host, Port, DisplayName);

    if (UGameInstance* GI = GetGameInstance())
    {
        if (UBlackjackNetClient* Net = GI->GetSubsystem<UBlackjackNetClient>())
        {
            Net->Connect(Host, Port, DisplayName);
        }
    }
}
