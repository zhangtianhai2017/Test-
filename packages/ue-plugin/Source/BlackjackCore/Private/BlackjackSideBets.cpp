#include "BlackjackSideBets.h"
#include "BlackjackHand.h"

namespace Blackjack
{
    FSideBetResult EvalPerfectPairs(const TArray<FCard>& PlayerTwo)
    {
        if (PlayerTwo.Num() < 2) return { 0, TEXT("—") };
        const FCard& A = PlayerTwo[0];
        const FCard& B = PlayerTwo[1];
        if (A.Rank != B.Rank) return { 0, TEXT("—") };
        if (A.Suit == B.Suit) return { 30, TEXT("Perfect Pair 30:1") };
        if (IsRed(A) == IsRed(B)) return { 10, TEXT("Colored Pair 10:1") };
        return { 5, TEXT("Mixed Pair 5:1") };
    }

    static bool SuitedAll(const TArray<FCard>& Cs)
    {
        for (const FCard& C : Cs) if (C.Suit != Cs[0].Suit) return false;
        return true;
    }

    static bool Consecutive(const TArray<FCard>& Cs)
    {
        TArray<int32> V; V.Reserve(Cs.Num());
        for (const FCard& C : Cs) V.Add(C.Rank == ERank::Ace ? 1 : RankValue(C.Rank));
        V.Sort();
        bool bLowA = true;
        for (int32 I = 1; I < V.Num(); ++I) if (V[I] - V[I-1] != 1) { bLowA = false; break; }
        if (bLowA) return true;
        // try ace-high
        TArray<int32> W; W.Reserve(Cs.Num());
        for (const FCard& C : Cs) W.Add(C.Rank == ERank::Ace ? 14 : RankValue(C.Rank));
        W.Sort();
        for (int32 I = 1; I < W.Num(); ++I) if (W[I] - W[I-1] != 1) return false;
        return true;
    }

    FSideBetResult EvalTwentyOnePlusThree(const TArray<FCard>& PlayerTwo, const FCard& DealerUp, bool bHaveDealer)
    {
        if (PlayerTwo.Num() < 2 || !bHaveDealer) return { 0, TEXT("—") };
        TArray<FCard> Three = { PlayerTwo[0], PlayerTwo[1], DealerUp };
        bool bSameRank = (Three[0].Rank == Three[1].Rank) && (Three[1].Rank == Three[2].Rank);
        bool bSuited = SuitedAll(Three);
        bool bConsec = Consecutive(Three);
        if (bSameRank && bSuited) return { 100, TEXT("Suited Trips 100:1") };
        if (bSuited && bConsec)   return { 40,  TEXT("Straight Flush 40:1") };
        if (bSameRank)            return { 30,  TEXT("Three of a Kind 30:1") };
        if (bConsec)              return { 10,  TEXT("Straight 10:1") };
        if (bSuited)              return { 5,   TEXT("Flush 5:1") };
        return { 0, TEXT("—") };
    }

    FSideBetResult EvalLuckyLadies(const TArray<FCard>& PlayerTwo, const TArray<FCard>& DealerFull)
    {
        if (PlayerTwo.Num() < 2) return { 0, TEXT("—") };
        const FCard& A = PlayerTwo[0];
        const FCard& B = PlayerTwo[1];
        const int32 Total = (A.Rank == ERank::Ace ? 1 : RankValue(A.Rank)) + (B.Rank == ERank::Ace ? 1 : RankValue(B.Rank));
        const bool bIsTwenty =
            (A.Rank == ERank::Ace && RankValue(B.Rank) == 10) ||
            (B.Rank == ERank::Ace && RankValue(A.Rank) == 10) ||
            (RankValue(A.Rank) == 10 && RankValue(B.Rank) == 10) ||
            Total == 20;

        auto IsQHearts = [](const FCard& C) { return C.Rank == ERank::Queen && C.Suit == ESuit::Hearts; };
        if (IsQHearts(A) && IsQHearts(B))
        {
            const bool bDealerBJ = DealerFull.Num() == 2 &&
                ((DealerFull[0].Rank == ERank::Ace && RankValue(DealerFull[1].Rank) == 10) ||
                 (DealerFull[1].Rank == ERank::Ace && RankValue(DealerFull[0].Rank) == 10));
            if (bDealerBJ) return { 1000, TEXT("QQ♥ + Dealer BJ 1000:1") };
            return { 200, TEXT("Pair of Queen of Hearts 200:1") };
        }
        if (!bIsTwenty) return { 0, TEXT("—") };
        if (A.Rank == B.Rank && A.Suit == B.Suit) return { 125, TEXT("Matched 20 125:1") };
        if (A.Suit == B.Suit) return { 19, TEXT("Suited 20 19:1") };
        if (IsRed(A) == IsRed(B)) return { 9, TEXT("Colored 20 9:1") };
        return { 4, TEXT("Any 20 4:1") };
    }
}
