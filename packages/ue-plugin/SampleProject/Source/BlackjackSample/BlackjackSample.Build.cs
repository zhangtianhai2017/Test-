using UnrealBuildTool;

public class BlackjackSample : ModuleRules
{
    public BlackjackSample(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] {
            "Core", "CoreUObject", "Engine", "InputCore",
            "BlackjackCore", "BlackjackUE"
        });
    }
}
