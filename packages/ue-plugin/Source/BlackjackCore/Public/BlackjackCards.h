#pragma once

#include "CoreMinimal.h"

namespace Blackjack
{
    enum class ESuit : uint8 { Spades, Hearts, Diamonds, Clubs };
    enum class ERank : uint8 { Ace, Two, Three, Four, Five, Six, Seven, Eight, Nine, Ten, Jack, Queen, King };

    struct FCard
    {
        ERank Rank;
        ESuit Suit;
        bool operator==(const FCard& O) const { return Rank == O.Rank && Suit == O.Suit; }
    };

    BLACKJACKCORE_API const TCHAR* SuitToChar(ESuit S);
    BLACKJACKCORE_API const TCHAR* RankToChar(ERank R);
    BLACKJACKCORE_API bool IsRed(const FCard& C);
    BLACKJACKCORE_API int32 RankValue(ERank R);

    /** mulberry32 — bit-identical to TS engine/src/rng.ts */
    class BLACKJACKCORE_API FRng
    {
    public:
        explicit FRng(uint32 Seed) : State(Seed), OriginalSeed(Seed) {}
        double Next();
        uint32 Seed() const { return OriginalSeed; }
    private:
        uint32 State;
        uint32 OriginalSeed;
    };

    BLACKJACKCORE_API TArray<FCard> BuildDeck(int32 Decks, bool bRemoveTens);
    BLACKJACKCORE_API void FisherYates(TArray<FCard>& Cards, FRng& Rng);

    class BLACKJACKCORE_API FShoe
    {
    public:
        FShoe(FRng& InRng, int32 Decks, double Penetration, bool bRemoveTens);
        FCard Draw();
        int32 Remaining() const { return Cards.Num() - Drawn; }
        bool NeedsShuffle() const { return Drawn >= Cut; }
        void Reshuffle();

    private:
        void Fill();
        FRng* Rng;
        int32 DeckCount;
        double PenetrationRatio;
        bool bRemoveTensFromShoe;
        TArray<FCard> Cards;
        int32 Cut = 0;
        int32 Drawn = 0;
    };
}
