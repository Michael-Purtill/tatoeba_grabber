import std.stdio;
import std.format;
import std.json;
import requests;
import std.algorithm;
import std.getopt;
import std.file;

const string apiUrl = "https://tatoeba.org/en/api_v0/search";
const string audioApiUrl = "https://tatoeba.org/en/audio/download/";

int main(string[] args)
{
	// API OPTIONS
	string langFrom = "";
	string langTo = "";
	bool hasAudio = false;
	long pageCount = 0;
	string directory = "./tatoeba_results";

	getopt(args,
		"l|lang", &langFrom,
		"a|audio", &hasAudio,
		"d|destination", &directory
	);

	auto statsRes = getContent(apiUrl, [
			"from": langFrom,
			"has_audio": hasAudio ? "yes": "no",
			"query": "",
			"to": "",
			"page": "1" // seems like tatoeba's api is 1-indexed.
		]);

	JSONValue statsJson = parseJSON(statsRes.toString());

	JSONValue paging = statsJson["paging"];

	pageCount = paging["Sentences"]["pageCount"].integer;

	try
	{
		mkdir(directory);
	}
	catch (Exception e)
	{
		writeln("couldn't create directory %s".format(directory));
		return 1;
	}

	foreach (i; 1 .. (pageCount + 1))
	{
		auto res = getContent(apiUrl, [
				"from": "jpn",
				"has_audio": "yes",
				"query": "",
				"to": "",
				"page": "%d".format(i)
			]);

		JSONValue jsonContent = parseJSON(res.toString());

		JSONValue sentences = jsonContent["results"];

		foreach (s; sentences.array())
		{
			string text = s["text"].str;
			long audioId = s["audios"][0]["id"].integer;
			string audioUrl = "%s%d".format(audioApiUrl, audioId);

			File file = File(directory ~ "/" ~ text ~ ".txt", "w+");

			file.writeln(text);
		}
	}

	return 0;
}
