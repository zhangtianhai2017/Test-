// UE Automation Spec: loads shared JSON vectors produced by packages/conformance
// and asserts that the C++ engine replays them with identical outcomes.
#if WITH_DEV_AUTOMATION_TESTS

#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Interfaces/IPluginManager.h"

#include "BlackjackGame.h"
#include "BlackjackCards.h"

using namespace Blackjack;

namespace
{
    FString VectorDir()
    {
        const TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("Blackjack"));
        if (Plugin.IsValid())
        {
            return FPaths::Combine(Plugin->GetBaseDir(), TEXT("../conformance/vectors"));
        }
        return FPaths::ProjectDir() / TEXT("../../packages/conformance/vectors");
    }

    ERuleSetId ParseRuleSet(const FString& S)
    {
        if (S == TEXT("SPANISH21")) return ERuleSetId::Spanish21;
        if (S == TEXT("PONTOON")) return ERuleSetId::Pontoon;
        if (S == TEXT("SUPER_FUN_21")) return ERuleSetId::SuperFun21;
        return ERuleSetId::Vegas;
    }

    EActionType ParseAction(const FString& S)
    {
        if (S == TEXT("PLACE_BET")) return EActionType::PlaceBet;
        if (S == TEXT("HIT"))       return EActionType::Hit;
        if (S == TEXT("STAND"))     return EActionType::Stand;
        if (S == TEXT("DOUBLE"))    return EActionType::Double;
        if (S == TEXT("SPLIT"))     return EActionType::Split;
        if (S == TEXT("SURRENDER")) return EActionType::Surrender;
        if (S == TEXT("INSURE"))    return EActionType::Insure;
        if (S == TEXT("DECLINE_INSURANCE")) return EActionType::DeclineInsurance;
        if (S == TEXT("NEW_ROUND")) return EActionType::NewRound;
        if (S == TEXT("SET_RULESET")) return EActionType::SetRuleSet;
        return EActionType::Stand;
    }

    FString OutcomeToString(EOutcome O)
    {
        switch (O)
        {
            case EOutcome::Win: return TEXT("win");
            case EOutcome::Loss: return TEXT("loss");
            case EOutcome::Push: return TEXT("push");
            case EOutcome::Blackjack: return TEXT("blackjack");
            case EOutcome::Surrender: return TEXT("surrender");
            case EOutcome::Bust: return TEXT("bust");
        }
        return TEXT("");
    }
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FBlackjackConformanceTest,
    "Blackjack.Conformance.ReplayVectors",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FBlackjackConformanceTest::RunTest(const FString& /*Parameters*/)
{
    const FString IndexPath = FPaths::Combine(VectorDir(), TEXT("index.json"));
    FString IndexText;
    if (!FFileHelper::LoadFileToString(IndexText, *IndexPath))
    {
        AddError(FString::Printf(TEXT("cannot load %s"), *IndexPath));
        return false;
    }
    TSharedPtr<FJsonObject> IndexJson;
    TSharedRef<TJsonReader<>> IndexReader = TJsonReaderFactory<>::Create(IndexText);
    if (!FJsonSerializer::Deserialize(IndexReader, IndexJson) || !IndexJson.IsValid())
    {
        AddError(TEXT("bad index.json"));
        return false;
    }

    const TArray<TSharedPtr<FJsonValue>>& Vectors = IndexJson->GetArrayField(TEXT("vectors"));
    for (const TSharedPtr<FJsonValue>& V : Vectors)
    {
        const TSharedPtr<FJsonObject>& VO = V->AsObject();
        const FString File = VO->GetStringField(TEXT("file"));
        const FString Path = FPaths::Combine(VectorDir(), File);
        FString Text;
        if (!FFileHelper::LoadFileToString(Text, *Path)) { AddError(Path); continue; }
        TSharedPtr<FJsonObject> Vector;
        TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
        if (!FJsonSerializer::Deserialize(Reader, Vector) || !Vector.IsValid()) { AddError(Path); continue; }

        const ERuleSetId Rs = ParseRuleSet(Vector->GetStringField(TEXT("ruleSetId")));
        const uint32 Seed = static_cast<uint32>(Vector->GetIntegerField(TEXT("seed")));
        const int32 ExpectedBankroll = Vector->GetIntegerField(TEXT("finalBankroll"));

        FGame Game(Rs, Seed);
        const TArray<TSharedPtr<FJsonValue>>& Steps = Vector->GetArrayField(TEXT("steps"));
        for (const TSharedPtr<FJsonValue>& Sv : Steps)
        {
            const TSharedPtr<FJsonObject>& So = Sv->AsObject();
            const TSharedPtr<FJsonObject>& Action = So->GetObjectField(TEXT("action"));
            FAction A;
            A.Type = ParseAction(Action->GetStringField(TEXT("type")));
            if (Action->HasField(TEXT("amount"))) A.Amount = Action->GetIntegerField(TEXT("amount"));
            Game.Dispatch(A);
        }
        while (Game.GetState().Phase == EPhase::PlayerTurn)
        {
            FAction S; S.Type = EActionType::Stand; Game.Dispatch(S);
        }

        const FSnapshot End = Game.GetState();
        TestEqual(FString::Printf(TEXT("[%s] bankroll"), *File), End.Bankroll, ExpectedBankroll);

        const TArray<TSharedPtr<FJsonValue>>& ExpResults = Vector->GetArrayField(TEXT("finalResults"));
        TestEqual(FString::Printf(TEXT("[%s] result count"), *File), End.RoundResults.Num(), ExpResults.Num());
        for (int32 I = 0; I < FMath::Min(End.RoundResults.Num(), ExpResults.Num()); ++I)
        {
            const TSharedPtr<FJsonObject>& Er = ExpResults[I]->AsObject();
            TestEqual(FString::Printf(TEXT("[%s] result[%d] outcome"), *File, I),
                      OutcomeToString(End.RoundResults[I].Outcome),
                      Er->GetStringField(TEXT("outcome")));
            TestEqual(FString::Printf(TEXT("[%s] result[%d] payout"), *File, I),
                      End.RoundResults[I].Payout,
                      Er->GetIntegerField(TEXT("payout")));
            TestEqual(FString::Printf(TEXT("[%s] result[%d] total"), *File, I),
                      End.RoundResults[I].Total,
                      Er->GetIntegerField(TEXT("total")));
        }
    }
    return true;
}

#endif
