using UnrealBuildTool;

public class BlackjackSample : ModuleRules
{
    public BlackjackSample(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        bUseUnity = false;
        PublicDependencyModuleNames.AddRange(new string[] {
            "Core", "CoreUObject", "Engine", "InputCore",
            "EnhancedInput",
            "BlackjackCore", "BlackjackUE"
        });
    }
}
